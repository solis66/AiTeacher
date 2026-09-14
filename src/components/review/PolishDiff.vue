<template>
  <div class="diff-overlay" @click.self="close">
    <div class="diff-dialog">
      <!-- 头部：标题 + 图例 + 关闭 -->
      <div class="diff-header">
        <span class="diff-title">润色对比</span>
        <div class="diff-legend">
          <span class="legend-item"><i class="dot dot--same"></i>未改内容</span>
          <span class="legend-item"><i class="dot dot--add"></i>新增</span>
          <span class="legend-item"><i class="dot dot--del"></i>删除（含删除线）</span>
        </div>
        <button type="button" class="ui-icon-btn" data-tip="关闭" @click="close">
          <X :size="16" />
        </button>
      </div>

      <!-- 正文：左原文 / 右润色稿；窄屏自动改为上下布局 -->
      <div class="diff-body">
        <section class="diff-col">
          <header class="diff-col-title">原文</header>
          <div class="diff-text">
            <p v-for="(row, i) in rows" :key="`l-${i}`" class="diff-para">
              <template v-if="row.left.length">
                <span
                  v-for="(seg, j) in row.left"
                  :key="j"
                  :class="seg.type === 'del' ? 'seg-del' : ''"
                >{{ seg.text }}</span>
              </template>
              <template v-else>&nbsp;</template>
            </p>
          </div>
        </section>

        <section class="diff-col">
          <header class="diff-col-title">润色后</header>
          <div class="diff-text">
            <p v-for="(row, i) in rows" :key="`r-${i}`" class="diff-para">
              <template v-if="row.right.length">
                <span
                  v-for="(seg, j) in row.right"
                  :key="j"
                  :class="seg.type === 'add' ? 'seg-add' : ''"
                >{{ seg.text }}</span>
              </template>
              <template v-else>&nbsp;</template>
            </p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 润色对比弹窗
 *
 * 需求对应：
 * - 弹窗内左右分别展示「原文」与「当前润色稿」
 * - 保持段落结构（按行/段做差异，不把整篇揉成一段）
 * - 未改内容用正文色，新增内容蓝色，删除内容橙色 + 删除线，并提供图例
 * - 窄屏改为上下布局（见 CSS 媒体查询）
 *
 * 实现说明：
 * - 先按「段落」做差异（diffLines），保证段落结构一致；
 * - 对同一段落内有改动的部分，再在段落内部做字符级差异（diffChars），
 *   这样中文改写能精确到字，而不是整段标红。
 */

import { computed } from 'vue';
import { diffLines, diffChars } from 'diff';
import { X } from 'lucide-vue-next';

const props = defineProps({
  original: { type: String, default: '' },
  polishedTitle: { type: String, default: '' },
  polishedText: { type: String, default: '' }
});

const emit = defineEmits(['close']);
const close = () => emit('close');

/** 把文本拆成非空行，保留段落粒度 */
const toLines = (text) => String(text || '').replace(/\r\n/g, '\n').split('\n').filter((l) => l.trim());

/** 段落内字符级差异 → 左右两列的分段 */
const buildIntraLine = (oldLine, newLine) => {
  const left = [];
  const right = [];
  diffChars(oldLine, newLine).forEach((part) => {
    if (part.added) {
      right.push({ type: 'add', text: part.value });
    } else if (part.removed) {
      left.push({ type: 'del', text: part.value });
    } else {
      left.push({ type: 'same', text: part.value });
      right.push({ type: 'same', text: part.value });
    }
  });
  return { left, right };
};

/**
 * 行级差异 → 左右两列段落数组。
 * 连续「删除 + 新增」视为同一段的改写，做段内字符级对比以保证对齐。
 */
const rows = computed(() => {
  const oldLines = toLines(props.original);
  const newLines = toLines(props.polishedText);
  const parts = diffLines(oldLines.join('\n'), newLines.join('\n'));

  const result = [];
  let bufferRemoved = null;

  const flush = (addedText) => {
    if (bufferRemoved !== null && addedText !== null) {
      // 成对出现 → 段内细粒度对比
      const oldLinesArr = bufferRemoved.split('\n');
      const newLinesArr = addedText.split('\n');
      const size = Math.max(oldLinesArr.length, newLinesArr.length);
      for (let i = 0; i < size; i += 1) {
        const o = oldLinesArr[i] ?? '';
        const n = newLinesArr[i] ?? '';
        if (o && n) result.push(buildIntraLine(o, n));
        else if (o) result.push({ left: [{ type: 'del', text: o }], right: [] });
        else if (n) result.push({ left: [], right: [{ type: 'add', text: n }] });
      }
    } else if (bufferRemoved !== null) {
      bufferRemoved.split('\n').forEach((line) => {
        if (line) result.push({ left: [{ type: 'del', text: line }], right: [] });
      });
    } else if (addedText !== null) {
      addedText.split('\n').forEach((line) => {
        if (line) result.push({ left: [], right: [{ type: 'add', text: line }] });
      });
    }
    bufferRemoved = null;
  };

  parts.forEach((part) => {
    const lines = part.value.replace(/\n$/, '');
    if (part.removed) {
      // 删除段可能紧跟着新增段，先缓存等待配对
      if (bufferRemoved === null) bufferRemoved = lines;
      else { flush(null); bufferRemoved = lines; }
    } else if (part.added) {
      flush(lines);
    } else {
      flush(null);
      lines.split('\n').forEach((line) => {
        if (line) result.push({ left: [{ type: 'same', text: line }], right: [{ type: 'same', text: line }] });
      });
    }
  });
  flush(null);

  // 若润色稿带有独立标题，置于右侧首行作为提示
  if (props.polishedTitle && props.polishedTitle.trim()) {
    result.unshift({ left: [], right: [{ type: 'add', text: props.polishedTitle.trim() }] });
  }
  return result;
});
</script>

<style scoped>
.diff-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(32, 33, 36, .45);
}

.diff-dialog {
  display: flex;
  flex-direction: column;
  width: min(1100px, 100%);
  height: min(80vh, 820px);
  background: var(--c-bg);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-2);
  overflow: hidden;
}

.diff-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.diff-title { font-size: var(--fs-lg); font-weight: 600; }

.diff-legend { display: flex; align-items: center; gap: 14px; margin-left: auto; font-size: var(--fs-xs); color: var(--c-text-secondary); }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot--same { background: var(--c-text); }
.dot--add { background: var(--c-add); }
.dot--del { background: var(--c-del); }

.diff-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.diff-col { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.diff-col + .diff-col { border-left: 1px solid var(--c-border); }

.diff-col-title {
  padding: 8px 14px;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-secondary);
  background: var(--c-bg-subtle);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}

.diff-text {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  line-height: 1.9;
  font-size: var(--fs-md);
}

.diff-para { margin: 0 0 2px; white-space: pre-wrap; word-break: break-word; }

/* 新增：蓝色；删除：橙色 + 删除线；未改：正文色（继承） */
.seg-add { color: var(--c-add); }
.seg-del { color: var(--c-del); text-decoration: line-through; }

@media (max-width: 900px) {
  .diff-overlay { padding: 10px; }
  .diff-dialog { height: 88vh; }
  .diff-body { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
  .diff-col + .diff-col { border-left: none; border-top: 1px solid var(--c-border); }
  .diff-legend { display: none; }
}
</style>
