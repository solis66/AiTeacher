<template>
  <section class="report-page">
    <header class="page-head">
      <h2 class="page-title">学情报告</h2>
      <p class="page-sub">基于已完成批改结果计算的确定性数据，展示学业情况与趋势</p>
    </header>

    <div v-if="students.length > 1" class="student-switch">
      <label class="field inline">
        <span class="field-label">查看学生</span>
        <select v-model="student" class="ui-input" @change="loadProfile">
          <option v-for="s in students" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
    </div>

    <div v-if="!loaded" class="report-empty">
      <Loader2 v-if="loading" :size="22" class="spin" />
      <p>{{ loading ? '正在生成学情报告…' : '暂无批改数据，请先完成批改' }}</p>
    </div>

    <template v-else-if="profile">
      <div class="stat-grid">
        <div class="stat-card"><span class="stat-label">批改篇数</span><span class="stat-value">{{ profile.n_reviews || 0 }}</span></div>
        <div class="stat-card"><span class="stat-label">平均分</span><span class="stat-value">{{ formatScore(profile.avg_score) }}</span></div>
        <div class="stat-card"><span class="stat-label">最高分</span><span class="stat-value">{{ formatScore(profile.best_score) }}</span></div>
        <div class="stat-card"><span class="stat-label">最低分</span><span class="stat-value">{{ formatScore(profile.worst_score) }}</span></div>
        <div class="stat-card"><span class="stat-label">最近一次</span><span class="stat-value">{{ formatScore(profile.latest_score) }}</span></div>
      </div>

      <div class="card-block trend-block" v-if="profile.trend">
        <span class="block-title">成绩趋势</span>
        <p class="trend-text">
          <template v-if="profile.trend.direction === '样本不足'">{{ profile.trend.note }}</template>
          <template v-else>最近 {{ profile.trend.recent.length }} 次较此前<span class="trend-dir">{{ trendLabel }}</span>{{ trendDelta }}</template>
        </p>
      </div>

      <div class="card-block dim-block" v-if="Object.keys(profile.dim_rates || {}).length">
        <span class="block-title">各维度得分率</span>
        <div v-for="dim in orderedDims" :key="dim.name" class="dim-row">
          <span class="dim-name">{{ dim.name }}</span>
          <div class="dim-bar"><div class="dim-bar-fill" :style="{ width: (dim.rate * 100) + '%' }"></div></div>
          <span class="dim-meta">{{ dim.avg_score }}分 · {{ dim.n }}篇 · {{ Math.round(dim.rate * 100) }}%</span>
        </div>
      </div>

      <div class="card-block" v-if="profile.weak_dims?.length || profile.strong_dims?.length">
        <span class="block-title">维度强弱</span>
        <p class="dim-tags">
          <template v-if="profile.strong_dims?.length"><span class="tag ok">优势：{{ profile.strong_dims.join('、') }}</span></template>
          <template v-if="profile.weak_dims?.length"><span class="tag warn">薄弱：{{ profile.weak_dims.join('、') }}</span></template>
        </p>
      </div>

      <div class="card-block" v-if="profile.recurring_issues?.length">
        <span class="block-title">反复出现的问题</span>
        <ul class="plain-list">
          <li v-for="(item, i) in profile.recurring_issues" :key="i">{{ item.aspect }}（{{ item.count }}篇提到）</li>
        </ul>
      </div>

      <div class="card-block" v-if="profile.recurring_strengths?.length">
        <span class="block-title">相对稳定的优点</span>
        <ul class="plain-list">
          <li v-for="(item, i) in profile.recurring_strengths" :key="i">{{ item.aspect }}（{{ item.count }}篇）</li>
        </ul>
      </div>

      <div class="card-block" v-if="profile.scores?.length">
        <span class="block-title">近期篇章</span>
        <ul class="score-list">
          <li v-for="(s, i) in profile.scores.slice().reverse()" :key="i">
            <span class="score-date">{{ s.date }}</span>
            <span class="score-title">《{{ s.title || '未命题' }}》</span>
            <span class="score-score">{{ s.score }}分{{ s.rating ? ' · ' + s.rating : '' }}</span>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>

<script setup>
/**
 * 学情报告（需求用户界面：登录后查学情）
 * 数据全部由后端直接计算（平均分/最高/最低/最近/趋势/维度得分率），不含模拟数据。
 */
import { ref, computed, onMounted } from 'vue';
import { Loader2 } from 'lucide-vue-next';
import request from '../../api/request.js';

const props = defineProps({ username: { type: String, default: '' } });

const students = ref([]);
const student = ref('');
const profile = ref(null);
const loading = ref(false);
const loaded = ref(false);

const ownerHeader = () => ({ 'X-Username': props.username || 'anonymous' });

const formatScore = (v) => (v === null || v === undefined ? '—' : `${v}分`);

/**
 * 维度得分率列表。
 *
 * 注意：这里必须摊平成「带 name 字段的对象数组」，不能直接返回 Object.entries() 的
 * [name, info] 二元组。Vue 的 v-for 在数组上把第二个变量当作**下标**而不是解构出来的
 * key，直接写 `v-for="(info, name) in orderedDims"` 会拿到 name=0/1/2/3/4、
 * info=['书面', {...}]，表现为维度名显示成数字、各项数值全是 NaN。
 *
 * 排序：得分率由低到高（与后端 render_profile 的口径一致，最该补的排最上面）。
 */
const orderedDims = computed(() => {
  const map = profile.value?.dim_rates || {};
  return Object.entries(map)
    .map(([name, info]) => ({ name, ...info }))
    .sort((a, b) => (a.rate ?? 0) - (b.rate ?? 0));
});

const trendDelta = computed(() => {
  const t = profile.value?.trend;
  if (!t || t.direction === '样本不足' || t.delta === null || t.delta === undefined) return '';
  return `（${Math.abs(t.delta)}分）`;
});
const trendLabel = computed(() => {
  const t = profile.value?.trend;
  return t?.direction === '上升' ? '成绩有所上升' : t?.direction === '下降' ? '成绩有所下滑' : '保持平稳';
});

const loadStudents = async () => {
  try {
    const res = await request.get('/api/review/students', { headers: ownerHeader() });
    if (res.data.success) students.value = res.data.data || [];
  } catch (e) { /* 名单加载失败不阻塞 */ }
};

const loadProfile = async () => {
  loading.value = true;
  try {
    const params = student.value && student.value !== props.username ? { student: student.value } : {};
    const res = await request.get('/api/review/profile', { headers: ownerHeader(), params });
    if (res.data.success) {
      profile.value = res.data.data;
      loaded.value = res.data.data?.has_data ?? false;
    } else {
      profile.value = null; loaded.value = false;
    }
  } catch (e) {
    profile.value = null; loaded.value = false;
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  await loadStudents();
  if (students.value.length > 1) student.value = students.value[0];
  await loadProfile();
});
</script>

<style scoped>
.report-page { max-width: 820px; margin: 0 auto; padding: 24px 28px 48px; overflow-y: auto; height: 100%; }
.page-head { margin-bottom: 16px; }
.page-title { font-size: var(--fs-xl); font-weight: 700; margin-bottom: 4px; }
.page-sub { font-size: var(--fs-sm); color: var(--c-text-secondary); margin: 0; }
.student-switch { margin-bottom: 16px; }
.field.inline { flex-direction: row; align-items: center; gap: 10px; }
.field-label { font-size: var(--fs-xs); color: var(--c-text-secondary); }

.report-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 60px; color: var(--c-text-muted); }

.stat-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); padding: 16px 14px; display: flex; flex-direction: column; gap: 6px; }
.stat-label { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.stat-value { font-size: var(--fs-lg); font-weight: 700; color: var(--c-primary); }

.card-block { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); padding: 16px 18px; margin-bottom: 14px; }
.block-title { display: block; font-size: var(--fs-md); font-weight: 600; margin-bottom: 10px; }
.trend-text { font-size: var(--fs-sm); color: var(--c-text); margin: 0; }
.trend-dir { font-weight: 600; color: var(--c-primary); margin: 0 2px; }

.dim-row { display: grid; grid-template-columns: 56px 1fr 110px; align-items: center; gap: 12px; margin-bottom: 8px; }
.dim-name { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.dim-bar { height: 10px; background: var(--c-bg-muted); border-radius: var(--r-pill); overflow: hidden; }
.dim-bar-fill { height: 100%; background: var(--c-primary); border-radius: var(--r-pill); }
.dim-meta { font-size: 12px; color: var(--c-text-muted); text-align: right; }
.dim-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.tag { padding: 3px 10px; font-size: var(--fs-xs); border-radius: var(--r-pill); }
.tag.ok { color: var(--c-ok); background: var(--c-ok-soft); }
.tag.warn { color: var(--c-warn); background: var(--c-warn-soft); }

.plain-list { margin: 0; padding-left: 18px; font-size: var(--fs-sm); color: var(--c-text); }
.score-list { list-style: none; margin: 0; padding: 0; font-size: var(--fs-sm); }
.score-list li { display: flex; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--c-border); }
.score-list li:last-child { border-bottom: none; }
.score-date { color: var(--c-text-muted); flex-shrink: 0; }
.score-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.score-score { color: var(--c-primary); font-weight: 600; flex-shrink: 0; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>