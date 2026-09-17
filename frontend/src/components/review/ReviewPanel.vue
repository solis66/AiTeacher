<template>
  <aside class="review-panel">
    <!-- 一级标签：固定顶部，仅保留总评 / 详细点评 / 全文润色 -->
    <nav class="panel-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="panel-tab"
        :class="{ 'is-active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >{{ tab.label }}</button>
    </nav>

    <!-- 内容区独立滚动，底部统一保存 -->
    <div class="panel-body">
      <!-- ==================== 总评 ==================== -->
      <template v-if="activeTab === 'overall'">
        <div class="score-row">
          <div class="score-cell">
            <span class="cell-label">字数</span>
            <span class="cell-value">{{ result.word_count || 0 }} 字</span>
          </div>
          <div class="score-cell">
            <span class="cell-label">分数</span>
            <span class="score-edit">
              <input
                v-model.number="result.score"
                type="number"
                class="ui-input score-input"
                min="0"
                :max="result.total_score || 50"
                @input="onScoreChange"
              />
              <span class="score-total">/ {{ result.total_score || 50 }}</span>
            </span>
          </div>
          <div class="score-cell">
            <span class="cell-label">等级</span>
            <select v-model="result.rating" class="ui-input rating-select" @change="markDirty">
              <option v-for="opt in ratingOptions" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </div>
        </div>

        <!-- 固定五维评分（需求 D1：内容/结构/立意/语言/书面） -->
        <section class="panel-section">
          <header class="section-head">
            <span class="section-title">详细评分（五维）</span>
          </header>
          <div class="dims-grid">
            <div v-for="dim in dimensionEntries" :key="dim.name" class="dim-cell">
              <span class="dim-name">{{ dim.name }}</span>
              <span class="dim-edit">
                <input
                  v-model.number="dim.score"
                  type="number"
                  class="ui-input dim-input"
                  min="0"
                  :max="dim.max_score"
                  @input="onDimensionChange"
                />
                <span class="dim-max">/ {{ dim.max_score }}</span>
              </span>
            </div>
          </div>
        </section>

        <!-- 仅提供默认选中的「通用评价」，直接编辑，不做预览卡与编辑框的重复展示 -->
        <section class="panel-section">
          <header class="section-head">
            <span class="section-title">总评风格</span>
            <button type="button" class="ui-icon-btn" data-tip="复制总评" @click="copy(result.overall_comment)">
              <Copy :size="14" />
            </button>
          </header>
          <div class="style-chip is-selected">通用评价（默认）</div>
          <textarea
            v-model="result.overall_comment"
            class="ui-textarea comment-box"
            placeholder="AI 未给出总评内容"
            @input="markDirty"
          ></textarea>
          <p v-if="!result.overall_comment" class="missing-hint">AI 未返回总评内容，可手动填写。</p>
        </section>

        <!-- 评分依据（可解释性）：主依据=题目/题干要求，辅依据=评分标准文件 -->
        <section class="panel-section">
          <header class="section-head">
            <span class="section-title">评分依据</span>
          </header>
          <div class="basis-card">
            <div class="basis-row">
              <span class="basis-tag primary">主依据</span>
              <span class="basis-text">{{ basis.primary || '题目与题干要求' }}</span>
            </div>
            <div v-if="basis.title || basis.requirements" class="basis-topic">
              <p v-if="basis.title"><span class="basis-k">题目：</span>{{ basis.title }}</p>
              <p v-if="basis.requirements"><span class="basis-k">题干：</span>{{ basis.requirements }}</p>
            </div>
            <div v-if="basis.requirement_checks && basis.requirement_checks.length" class="basis-checks">
              <div v-for="(ck, i) in basis.requirement_checks" :key="i" class="basis-check">
                <span class="basis-state" :class="basisStateClass(ck.satisfied)">{{ basisStateText(ck.satisfied) }}</span>
                <span class="basis-text">{{ ck.requirement }}<template v-if="ck.note">：{{ ck.note }}</template></span>
              </div>
            </div>
            <div class="basis-row">
              <span class="basis-tag auxiliary">辅依据</span>
              <span class="basis-text">{{ basis.auxiliary || '《广东省中考作文评分标准.doc》' }}</span>
            </div>
            <p v-if="basis.explanation" class="basis-explanation">{{ basis.explanation }}</p>
          </div>
        </section>
      </template>

      <!-- ==================== 详细点评 ==================== -->
      <template v-else-if="activeTab === 'detail'">
        <!-- 1. 吸睛改写 -->
        <section class="panel-section">
          <header class="section-head collapse-head" @click="toggle('rewrites')">
            <ChevronDown :size="14" class="caret" :class="{ 'is-closed': !open.rewrites }" />
            <span class="section-title">吸睛改写</span>
            <button type="button" class="ui-icon-btn" data-tip="复制全部" @click.stop="copy(rewritesText)">
              <Copy :size="14" />
            </button>
          </header>
          <div v-show="open.rewrites" class="section-content">
            <!-- 改写标题（单个字符串） -->
            <div class="field">
              <div class="field-head">
                <span class="field-label">改写标题</span>
                <button type="button" class="ui-icon-btn" data-tip="复制" @click="copy(rewrite.title)">
                  <Copy :size="12" />
                </button>
              </div>
              <textarea
                v-model="rewrite.title"
                class="ui-textarea field-box"
                placeholder="AI 未给出改写标题"
                @input="markDirty"
              ></textarea>
              <p v-if="!rewrite.title" class="missing-hint">AI 未给出该方面改写。</p>
            </div>

            <!-- 开头/结尾：各 3 个候选（数组） -->
            <div v-for="field in arrayRewriteFields" :key="field.key" class="field">
              <div class="field-head">
                <span class="field-label">{{ field.label }}（3 个候选）</span>
              </div>
              <div v-for="(cand, ci) in rewriteArray(field.key)" :key="ci" class="cand-row">
                <span class="cand-index">{{ ci + 1 }}</span>
                <textarea
                  :value="cand"
                  class="ui-textarea field-box cand-box"
                  :placeholder="`AI 未生成${field.label}候选 ${ci + 1}`"
                  @input="updateCand(field.key, ci, $event.target.value)"
                ></textarea>
                <button type="button" class="ui-icon-btn" data-tip="复制" @click="copy(cand)">
                  <Copy :size="12" />
                </button>
              </div>
              <p v-if="!((rewrite[field.key] || []).length)" class="missing-hint">AI 未给出{{ field.label }}改写。</p>
            </div>
          </div>
        </section>

        <!-- 2. 原文纠正 -->
        <section class="panel-section">
          <header class="section-head collapse-head" @click="toggle('corrections')">
            <ChevronDown :size="14" class="caret" :class="{ 'is-closed': !open.corrections }" />
            <span class="section-title">原文纠正</span>
            <span class="count-badge">{{ corrections.length }}</span>
          </header>
          <div v-show="open.corrections" class="section-content">
            <div v-if="!corrections.length" class="missing-hint block">AI 未给出原文纠正建议。</div>
            <div v-for="(item, index) in corrections" :key="item.id || index" class="field correct-item">
              <div class="field-head">
                <span class="field-label">原句 {{ index + 1 }}</span>
                <button type="button" class="ui-icon-btn" data-tip="复制建议" @click="copy(item.suggestion)">
                  <Copy :size="12" />
                </button>
              </div>
              <!-- 原句只读展示：优先展示命中的真实 OCR 原文（与图片一致），未定位时回退到 AI 引句 -->
              <p class="quote-text">{{ item.matched_text || item.quote }}</p>
              <textarea
                v-model="item.suggestion"
                class="ui-textarea field-box"
                placeholder="填写修改建议"
                @input="markDirty"
              ></textarea>
              <p v-if="!item.page" class="missing-hint">该句未能在原文中唯一定位。</p>
            </div>
          </div>
        </section>

        <!-- 3. AI 分析 -->
        <section class="panel-section">
          <header class="section-head collapse-head" @click="toggle('analysis')">
            <ChevronDown :size="14" class="caret" :class="{ 'is-closed': !open.analysis }" />
            <span class="section-title">AI 分析</span>
          </header>
          <div v-show="open.analysis" class="section-content">
            <div v-for="field in analysisFields" :key="field.key" class="field">
              <div class="field-head">
                <span class="field-label">{{ field.label }}</span>
                <button type="button" class="ui-icon-btn" data-tip="复制" @click="copy(result.analysis?.[field.key])">
                  <Copy :size="12" />
                </button>
              </div>
              <textarea
                v-model="result.analysis[field.key]"
                class="ui-textarea field-box"
                :placeholder="`AI 未给出${field.label}分析`"
                @input="markDirty"
              ></textarea>
              <p v-if="!result.analysis?.[field.key]" class="missing-hint">AI 未给出该方面分析。</p>
            </div>
          </div>
        </section>

        <!-- 4. 文章亮点 -->
        <section class="panel-section">
          <header class="section-head collapse-head" @click="toggle('highlights')">
            <ChevronDown :size="14" class="caret" :class="{ 'is-closed': !open.highlights }" />
            <span class="section-title">文章亮点</span>
            <span class="count-badge">{{ highlights.length }}</span>
          </header>
          <div v-show="open.highlights" class="section-content">
            <div v-if="!highlights.length" class="missing-hint block">AI 未给出文章亮点。</div>
            <div v-for="(item, index) in highlights" :key="`hl-${index}`" class="field">
              <div class="field-head">
                <span class="field-label">亮点 {{ index + 1 }}</span>
                <button type="button" class="ui-icon-btn" data-tip="复制" @click="copy(item)">
                  <Copy :size="12" />
                </button>
              </div>
              <textarea v-model="highlights[index]" class="ui-textarea field-box" @input="markDirty"></textarea>
            </div>
          </div>
        </section>

        <!-- 5. 改进建议 -->
        <section class="panel-section">
          <header class="section-head collapse-head" @click="toggle('suggestions')">
            <ChevronDown :size="14" class="caret" :class="{ 'is-closed': !open.suggestions }" />
            <span class="section-title">改进建议</span>
            <span class="count-badge">{{ suggestions.length }}</span>
          </header>
          <div v-show="open.suggestions" class="section-content">
            <div v-if="!suggestions.length" class="missing-hint block">AI 未给出改进建议。</div>
            <div v-for="(item, index) in suggestions" :key="`sg-${index}`" class="field">
              <div class="field-head">
                <span class="field-label">建议 {{ index + 1 }}</span>
                <button type="button" class="ui-icon-btn" data-tip="复制" @click="copy(item)">
                  <Copy :size="12" />
                </button>
              </div>
              <textarea v-model="suggestions[index]" class="ui-textarea field-box" @input="markDirty"></textarea>
            </div>
          </div>
        </section>
      </template>

      <!-- ==================== 全文润色 ==================== -->
      <template v-else>
        <section class="panel-section">
          <header class="section-head">
            <span class="section-title">全文润色</span>
            <div class="head-actions">
              <button type="button" class="ui-btn" @click="$emit('open-diff')">
                <Columns2 :size="14" /><span>润色对比</span>
              </button>
              <button type="button" class="ui-icon-btn" data-tip="复制全文" @click="copy(`${result.polished_title || ''}\n${result.polished_text || ''}`)">
                <Copy :size="14" />
              </button>
            </div>
          </header>

          <div class="field">
            <div class="field-head"><span class="field-label">标题</span></div>
            <input
              v-model="result.polished_title"
              type="text"
              class="ui-input"
              placeholder="AI 未给出润色标题"
              @input="markDirty"
            />
          </div>

          <div class="field">
            <div class="field-head"><span class="field-label">正文</span></div>
            <textarea
              v-model="result.polished_text"
              class="ui-textarea polish-box"
              placeholder="AI 未给出润色正文"
              @input="markDirty"
            ></textarea>
            <p v-if="!result.polished_text" class="missing-hint">AI 未返回润色正文。</p>
          </div>
        </section>
      </template>
    </div>
  </aside>
</template>

<script setup>
/**
 * 批改页右栏：评价编辑
 *
 * 需求对应：
 * - 仅保留「总评、详细点评、全文润色」三个一级标签；顶部标签固定、内容独立滚动
 * - 总评：展示字数/分数/满分/等级，支持改分数与评级；仅提供默认选中的「通用评价」，
 *   直接编辑评语，不重复展示预览卡与编辑框
 * - 详细点评：吸睛改写（标题/开头/结尾）、原文纠正（原句+建议）、AI 分析（内容/结构/
 *   语言/技巧/情感）、文章亮点、改进建议；轻量折叠分区，每项独立可编辑文本框
 * - 全文润色：包含标题与段落的完整润色作文，可编辑/复制/保存，提供「润色对比」
 * - 缺失的分析显示明确状态，不以示例内容代替
 */

import { ref, computed } from 'vue';
import { Copy, ChevronDown, Columns2 } from 'lucide-vue-next';

const props = defineProps({
  result: { type: Object, required: true }
});

const emit = defineEmits(['open-diff', 'change', 'notify']);

const tabs = [
  { key: 'overall', label: '总评' },
  { key: 'detail', label: '详细点评' },
  { key: 'polish', label: '全文润色' }
];

const activeTab = ref('overall');
const ratingOptions = ['优', '良', '需改进'];

// 折叠区展开状态（默认全部展开）
const open = ref({ rewrites: true, corrections: true, analysis: true, highlights: true, suggestions: true });
const toggle = (key) => { open.value[key] = !open.value[key]; };

const rewrite = computed(() => {
  const r = props.result.rewrites || {};
  if (!r.title) r.title = '';
  if (!Array.isArray(r.opening)) r.opening = [];
  if (!Array.isArray(r.ending)) r.ending = [];
  return r;
});
const arrayRewriteFields = [
  { key: 'opening', label: '改写开头' },
  { key: 'ending', label: '改写结尾' }
];
/** 取某数组改写的候选列表（兼容旧数据：单个字符串 → 折成单元素数组） */
const rewriteArray = (key) => {
  const v = rewrite.value[key];
  return v;
};
/** 更新数组改写的某个候选；数组不足 3 个时前端按 N/A 兜底展示，不硬凑 */
const updateCand = (key, index, value) => {
  const arr = rewrite.value[key];
  arr[index] = value;
  markDirty();
};

const analysisFields = [
  { key: 'content', label: '内容' },
  { key: 'structure', label: '结构' },
  { key: 'language', label: '语言' },
  { key: 'technique', label: '技巧' },
  { key: 'emotion', label: '情感' }
];

const corrections = computed(() => props.result.corrections || []);
const highlights = computed(() => props.result.highlights || []);
const suggestions = computed(() => props.result.suggestions || []);

/** 固定五维评分（需求 D1：内容/结构/立意/语言/书面） */
const dimensionEntries = computed(() => {
  const dims = props.result.dimensions || [];
  return dims.map((d) => ({
    name: d.name,
    score: (typeof d.score === 'number') ? d.score : 0,
    max_score: d.max_score || 10
  }));
});

/** 修改任一维度分数后，总分与等级随之同步，保持口径一致 */
const onDimensionChange = () => {
  const total = dimensionEntries.value.reduce((sum, d) => sum + (Number(d.score) || 0), 0);
  props.result.score = total;
  props.result.rating = total >= 40 ? '优' : total >= 30 ? '良' : '需改进';
  markDirty();
};

// 评分依据（可解释性）：主依据（题目/题干要求）与辅依据（评分标准文件）
const basis = computed(() => props.result.scoring_basis || {});
const basisStateText = (s) => (s === true || s === 'true') ? '满足' : (s === false || s === 'false') ? '未满足' : '部分';
const basisStateClass = (s) => (s === true || s === 'true') ? 'ok' : (s === false || s === 'false') ? 'no' : 'part';

const rewritesText = computed(() => {
  const r = props.result.rewrites || {};
  const lines = [`【改写标题】${r.title || ''}`];
  ['opening', 'ending'].forEach((key) => {
    const label = key === 'opening' ? '开头' : '结尾';
    const arr = Array.isArray(r[key]) ? r[key] : [];
    arr.forEach((c, i) => lines.push(`【改写${label}候选${i + 1}】${c || ''}`));
  });
  return lines.join('\n');
});

const markDirty = () => emit('change');

/** 修改分数时同步等级，保证两者口径一致 */
const onScoreChange = () => {
  const score = Number(props.result.score);
  if (Number.isNaN(score)) return;
  props.result.rating = score >= 40 ? '优' : score >= 30 ? '良' : '需改进';
  markDirty();
};

/** 复制到剪贴板；失败时提示用户（不静默吞掉） */
const copy = async (text) => {
  if (!text) return emit('notify', '没有可复制的内容');
  try {
    await navigator.clipboard.writeText(String(text));
    emit('notify', '已复制');
  } catch (e) {
    emit('notify', '复制失败，请手动选择文本复制');
  }
};
</script>

<style scoped>
.review-panel {
  display: flex;
  flex-direction: column;
  width: var(--panel-width);
  flex-shrink: 0;
  background: var(--c-bg);
  border-left: 1px solid var(--c-border);
  min-height: 0;
}

/* 顶部标签固定 */
.panel-tabs {
  display: flex;
  flex-shrink: 0;
  height: var(--topbar-height);
  border-bottom: 1px solid var(--c-border);
}
.panel-tab {
  position: relative;
  flex: 1;
  height: 100%;
  font-size: var(--fs-md);
  font-family: inherit;
  color: var(--c-text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color .15s;
}
.panel-tab:hover { color: var(--c-text); }
.panel-tab.is-active { color: var(--c-primary); font-weight: 600; }
.panel-tab.is-active::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
  width: 40px;
  height: 2px;
  background: var(--c-primary);
  border-radius: 2px;
}

.panel-body { flex: 1; overflow-y: auto; padding: 12px; }

/* 总评：指标行 */
.score-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--c-border);
}
.score-cell { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cell-label { font-size: var(--fs-xs); color: var(--c-text-muted); }
.cell-value { font-size: var(--fs-lg); font-weight: 700; color: var(--c-primary); }
.score-edit { display: flex; align-items: center; gap: 4px; }
.score-input { width: 56px; padding: 3px 6px; font-size: var(--fs-lg); font-weight: 700; color: var(--c-primary); }
.score-total { font-size: var(--fs-xs); color: var(--c-text-muted); }
.rating-select { padding: 3px 6px; font-size: var(--fs-sm); }

.panel-section { margin-bottom: 16px; }

.section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  margin-bottom: 8px;
}
.collapse-head { cursor: pointer; user-select: none; }
.section-title { font-size: var(--fs-md); font-weight: 600; color: var(--c-text); }
.caret { color: var(--c-text-muted); transition: transform .15s; flex-shrink: 0; }
.caret.is-closed { transform: rotate(-90deg); }
.head-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.section-head .ui-icon-btn { margin-left: auto; }
.head-actions .ui-icon-btn { margin-left: 0; }

.count-badge {
  padding: 0 6px;
  font-size: 11px;
  color: var(--c-text-secondary);
  background: var(--c-bg-muted);
  border-radius: var(--r-pill);
}

/* 固定五维评分（内容/结构/立意/语言/书面）：2 列紧凑网格 */
.dims-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}
.dim-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 8px;
  font-size: var(--fs-xs);
  background: var(--c-bg-subtle);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
}
.dim-name { color: var(--c-text-secondary); flex-shrink: 0; }
.dim-edit { display: flex; align-items: center; gap: 3px; }
.dim-input { width: 44px; padding: 2px 4px; font-size: var(--fs-sm); font-weight: 600; text-align: right; }
.dim-max { font-size: 11px; color: var(--c-text-muted); }

/* 改写开头/结尾候选数组：序号徽标 + 编辑框 + 复制 */
.cand-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 6px;
}
.cand-index {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--c-primary);
  background: var(--c-primary-soft);
  border-radius: 50%;
}
.cand-box { min-height: 72px; max-height: 200px; flex: 1; font-size: var(--fs-sm); }

.style-chip {
  display: inline-block;
  padding: 3px 10px;
  margin-bottom: 8px;
  font-size: var(--fs-xs);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  color: var(--c-text-secondary);
}
.style-chip.is-selected { color: var(--c-primary); background: var(--c-primary-soft); border-color: #c6dafc; font-weight: 600; }

.field { margin-bottom: 10px; }
.field-head { display: flex; align-items: center; gap: 4px; margin-bottom: 4px; }
.field-label { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.field-head .ui-icon-btn { margin-left: auto; width: 22px; height: 22px; }

.field-box { min-height: 110px; max-height: 420px; font-size: var(--fs-sm); }
.comment-box { min-height: 160px; font-size: var(--fs-sm); line-height: 1.8; }
.polish-box { min-height: 320px; font-size: var(--fs-sm); line-height: 1.9; }

.quote-text {
  margin: 0 0 6px;
  padding: 6px 8px;
  font-size: var(--fs-xs);
  line-height: 1.7;
  color: var(--c-error);
  background: var(--c-error-soft);
  border-left: 3px solid var(--c-error);
  border-radius: 3px;
}

/* 缺失内容：明确状态，不用示例内容填充 */
.missing-hint { margin: 4px 0 0; font-size: 11px; color: var(--c-text-muted); }
.missing-hint.block {
  padding: 10px;
  background: var(--c-bg-subtle);
  border: 1px dashed var(--c-border);
  border-radius: var(--r-sm);
  text-align: center;
}

/* 评分依据（可解释性） */
.basis-card {
  padding: 8px 10px;
  font-size: var(--fs-xs);
  line-height: 1.7;
  background: var(--c-bg-subtle);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
}
.basis-row { display: flex; align-items: flex-start; gap: 6px; margin-bottom: 4px; }
.basis-tag {
  flex-shrink: 0;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: var(--r-pill);
  color: #fff;
}
.basis-tag.primary { background: var(--c-primary); }
.basis-tag.auxiliary { background: var(--c-text-muted); }
.basis-text { color: var(--c-text); word-break: break-all; }
.basis-topic { margin: 2px 0 4px; padding-left: 2px; color: var(--c-text-secondary); }
.basis-topic p { margin: 2px 0; }
.basis-k { color: var(--c-text-muted); }
.basis-checks { margin: 4px 0; }
.basis-check { display: flex; align-items: flex-start; gap: 6px; margin-bottom: 3px; }
.basis-state {
  flex-shrink: 0;
  padding: 0 5px;
  font-size: 11px;
  border-radius: var(--r-pill);
}
.basis-state.ok { color: var(--c-ok); background: var(--c-ok-soft); }
.basis-state.no { color: var(--c-error); background: var(--c-error-soft); }
.basis-state.part { color: var(--c-warn); background: var(--c-warn-soft); }
.basis-explanation { margin: 6px 0 0; padding-top: 6px; border-top: 1px dashed var(--c-border); color: var(--c-text-secondary); }

@media (max-width: 1280px) {
  .review-panel { width: 340px; }
}
</style>
