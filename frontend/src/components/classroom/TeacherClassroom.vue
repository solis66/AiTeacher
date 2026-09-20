<template>
  <section class="classroom-page">
    <header class="page-head">
      <h2 class="page-title">班级管理</h2>
      <p class="page-sub">创建班级、发布作文训练，查看学生提交与班级学情</p>
    </header>

    <!-- 创建班级 -->
    <div class="create-bar">
      <input
        v-model="newClassName"
        class="ui-input"
        placeholder="输入班级名称，例如：九年级(3)班"
        maxlength="32"
        @keydown.enter="createClass"
      />
      <button
        type="button"
        class="ui-btn ui-btn--primary"
        :disabled="creating || !newClassName.trim()"
        @click="createClass"
      >
        <Plus :size="14" />
        <span>{{ creating ? '创建中…' : '创建班级' }}</span>
      </button>
    </div>

    <p v-if="error" class="tip tip--error">{{ error }}</p>
    <p v-if="notice" class="tip tip--ok">{{ notice }}</p>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!classes.length" class="empty">还没有班级，先创建一个吧</div>

    <div v-else class="class-grid">
      <button
        v-for="item in classes"
        :key="item.id"
        type="button"
        class="class-card"
        :class="{ 'is-active': item.id === activeId }"
        @click="selectClass(item.id)"
      >
        <span class="class-name">{{ item.name }}</span>
        <span class="class-code">邀请码 <b>{{ item.join_code }}</b></span>
        <span class="class-meta">{{ item.student_count }} 名学生 · {{ item.assignment_count }} 次作业</span>
      </button>
    </div>

    <!-- 班级详情 -->
    <div v-if="activeId" class="detail">
      <div class="tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          type="button"
          class="tab"
          :class="{ 'is-active': tab === t.key }"
          @click="switchTab(t.key)"
        >{{ t.label }}</button>
      </div>

      <!-- 学生名单 -->
      <div v-if="tab === 'members'" class="pane">
        <p class="pane-hint">把上面班级卡片里的邀请码发给学生，学生用「我的班级」输入即可加入。</p>
        <p v-if="!members.length" class="empty">还没有学生加入</p>
        <ul v-else class="row-list">
          <li v-for="m in members" :key="m.student" class="row">
            <span class="avatar">{{ (m.student || '?').charAt(0).toUpperCase() }}</span>
            <span class="row-main">{{ m.student }}</span>
            <span class="row-sub">{{ formatTime(m.joined_at) }} 加入</span>
            <button type="button" class="ui-text-btn danger" @click="removeMember(m.student)">移出</button>
          </li>
        </ul>
      </div>

      <!-- 作业管理 -->
      <div v-else-if="tab === 'assign'" class="pane">
        <div class="form-card">
          <input
            v-model="draft.title"
            class="ui-input"
            placeholder="作文题目，例如：那一刻，我长大了"
            maxlength="100"
          />
          <textarea
            v-model="draft.requirements"
            class="ui-textarea"
            rows="2"
            placeholder="题干要求，例如：不少于600字，结合自身经历"
          ></textarea>
          <div class="form-row">
            <select v-model="draft.grade" class="ui-input">
              <option value="">年级（可选）</option>
              <option v-for="g in grades" :key="g" :value="g">{{ g }}</option>
            </select>
            <select v-model="draft.essayType" class="ui-input">
              <option value="">体裁（可选，默认由AI判定）</option>
              <option v-for="t in essayTypes" :key="t" :value="t">{{ t }}</option>
            </select>
            <button
              type="button"
              class="ui-btn ui-btn--primary"
              :disabled="publishing || !draft.title.trim()"
              @click="publishAssignment"
            >
              <Send :size="14" />
              <span>{{ publishing ? '发布中…' : '发布作文训练' }}</span>
            </button>
          </div>
        </div>

        <p v-if="!assignments.length" class="empty">还没有发布作文训练</p>
        <ul v-else class="row-list">
          <li v-for="a in assignments" :key="a.id" class="row">
            <span class="row-main">{{ a.title }}</span>
            <span class="row-sub">
              {{ a.grade || '未指定年级' }}{{ a.essay_type ? ' · ' + a.essay_type : '' }}
            </span>
            <span class="progress">{{ a.submitted_count }} / {{ a.student_count }} 已交</span>
            <button type="button" class="ui-text-btn" @click="openAssignment(a)">查看提交</button>
            <button type="button" class="ui-text-btn danger" @click="deleteAssignment(a)">删除</button>
          </li>
        </ul>
      </div>

      <!-- 提交与学情 -->
      <div v-else class="pane">
        <div class="stat-row">
          <div class="stat"><b>{{ report?.member_count ?? 0 }}</b><span>班级人数</span></div>
          <div class="stat"><b>{{ report?.assignment_count ?? 0 }}</b><span>作文训练</span></div>
          <div class="stat"><b>{{ report?.submission_count ?? 0 }}</b><span>收到提交</span></div>
          <div class="stat"><b>{{ report?.avg_score ?? '—' }}</b><span>班级均分</span></div>
        </div>

        <h4 class="sub-title">学生学情（按平均分排序）</h4>
        <p v-if="!report?.students?.length" class="empty">暂无数据</p>
        <table v-else class="report-table">
          <thead>
            <tr>
              <th>学生</th><th>已提交</th><th>已完成</th>
              <th>平均分</th><th>最高分</th><th>最近得分</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in report.students" :key="s.student">
              <td>{{ s.student }}</td>
              <td>{{ s.submitted }}</td>
              <td>{{ s.finished }}</td>
              <td>{{ s.avg ?? '—' }}</td>
              <td>{{ s.best ?? '—' }}</td>
              <td>{{ s.latest_score ?? '—' }}</td>
            </tr>
          </tbody>
        </table>

        <h4 class="sub-title">
          提交明细
          <span v-if="filterAssignment" class="filter-tag">
            仅看《{{ filterAssignment.title }}》
            <button type="button" @click="filterAssignment = null">×</button>
          </span>
        </h4>
        <p v-if="!visibleSubmissions.length" class="empty">还没有学生提交</p>
        <ul v-else class="row-list">
          <li v-for="s in visibleSubmissions" :key="s.id" class="row">
            <span class="row-main">{{ s.student }}</span>
            <span class="row-sub">{{ s.title || '未填题目' }}</span>
            <span class="status" :class="'status--' + s.status">{{ statusLabel(s.status) }}</span>
            <span class="score">{{ s.score ?? '—' }} 分</span>
            <button
              type="button"
              class="ui-text-btn"
              :disabled="s.status !== 'done'"
              @click="viewSubmission(s)"
            >查看结果</button>
          </li>
        </ul>

        <template v-if="filterAssignment">
          <h4 class="sub-title">未提交名单</h4>
          <p v-if="!missing.length" class="empty">全班都已提交</p>
          <p v-else class="missing">{{ missing.join('、') }}</p>
        </template>
      </div>
    </div>

    <!-- 只读批改结果（老师代查看，数据来自受控接口） -->
    <div v-if="viewing" class="modal" @click.self="viewing = null">
      <div class="modal-card">
        <header class="modal-head">
          <h3>{{ viewing.student }} · {{ viewing.input?.title || '作文' }}</h3>
          <button type="button" class="modal-close" @click="viewing = null">×</button>
        </header>
        <div class="modal-body">
          <p v-if="viewingLoading" class="empty">加载中…</p>
          <template v-else>
            <p class="modal-score">
              得分 <b>{{ viewing.result?.score ?? '—' }}</b> / {{ viewing.result?.total_score ?? 50 }}
              <span v-if="viewing.result?.rating" class="rating">{{ viewing.result.rating }}</span>
            </p>
            <ul v-if="viewing.result?.dimensions?.length" class="dim-list">
              <li v-for="d in viewing.result.dimensions" :key="d.name">
                <span>{{ d.name }}</span>
                <b>{{ d.score }} / {{ d.max_score }}</b>
              </li>
            </ul>
            <p v-if="viewing.result?.overall_comment" class="comment">{{ viewing.result.overall_comment }}</p>
            <img
              v-if="viewing.thumb"
              class="page-img"
              :src="pageUrl(viewing.id, viewing.thumb, viewing.owner)"
              alt="作文原文"
            />
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
/**
 * 老师端「班级管理」
 *
 * 能力：建班（自动分配邀请码）→ 看学生名单 → 发布作文训练 →
 *       看每个作业的提交情况（含未交名单）→ 看班级学情与单份批改结果。
 *
 * 权限：所有请求都带 X-Username，服务端按 users.role 复核角色、
 *       按 classes.teacher 复核班级归属，前端不做也不该做权限判断。
 *       老师的学情只覆盖自己班级的作业。
 */
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { Plus, Send } from 'lucide-vue-next';
import request from '../../api/request.js';
import { reviewPageUrl } from '../../utils/reviewUrl.js';

const props = defineProps({ username: { type: String, default: '' } });
const emit = defineEmits(['error']);

const grades = ['七年级', '八年级', '九年级'];
const essayTypes = ['议论文', '记叙文', '说明文'];

const tabs = [
  { key: 'members', label: '学生名单' },
  { key: 'assign', label: '作业管理' },
  { key: 'report', label: '提交与学情' },
];

const classes = ref([]);
const loading = ref(false);
const error = ref('');
const notice = ref('');
const creating = ref(false);
const newClassName = ref('');
const activeId = ref(null);
const tab = ref('members');

const members = ref([]);
const assignments = ref([]);
const report = ref(null);
const submissions = ref([]);
const missing = ref([]);
const filterAssignment = ref(null);

const draft = reactive({ title: '', requirements: '', grade: '', essayType: '' });
const publishing = ref(false);

const viewing = ref(null);
const viewingLoading = ref(false);

const ownerHeader = () => ({ 'X-Username': props.username || 'anonymous' });

const active = computed(() => classes.value.find((c) => c.id === activeId.value) || null);
const visibleSubmissions = computed(() => {
  if (!filterAssignment.value) return submissions.value;
  const target = String(filterAssignment.value.id);
  return submissions.value.filter((s) => String(s.assignment_id || '') === target);
});

const flash = (message, isError = false) => {
  if (isError) {
    error.value = message;
    emit('error', message);
    setTimeout(() => { error.value = ''; }, 5000);
  } else {
    notice.value = message;
    setTimeout(() => { notice.value = ''; }, 3000);
  }
};

const formatTime = (value) => (value ? String(value).slice(0, 16).replace('T', ' ') : '');

const statusLabel = (status) => ({
  done: '已完成', failed: '失败', queued: '排队中',
  recognizing: '识别中', grading: '批改中',
}[status] || status || '');

const pageUrl = (id, file, owner) => reviewPageUrl(id, file, owner);

// ------------------------------------------------------------ 数据加载

const loadClasses = async () => {
  loading.value = true;
  try {
    const res = await request.get('/api/class/mine', { headers: ownerHeader() });
    classes.value = res.data.success ? (res.data.data || []) : [];
    if (!classes.value.some((c) => c.id === activeId.value)) {
      activeId.value = classes.value[0]?.id ?? null;
    }
  } catch (e) {
    flash(e.response?.data?.message || e.message || '加载班级失败', true);
  } finally {
    loading.value = false;
  }
};

const loadDetail = async () => {
  if (!activeId.value) {
    members.value = [];
    assignments.value = [];
    report.value = null;
    submissions.value = [];
    missing.value = [];
    return;
  }
  const cid = activeId.value;
  const headers = ownerHeader();
  try {
    // 一次并行取全，避免三个面板切换时各转一次圈
    const [m, a, r] = await Promise.all([
      request.get(`/api/class/${cid}/members`, { headers }),
      request.get(`/api/assignment/class/${cid}`, { headers }),
      request.get(`/api/class/${cid}/report`, { headers }),
    ]);
    members.value = m.data.data || [];
    assignments.value = a.data.data || [];
    report.value = r.data.data || null;

    const s = await request.get(`/api/class/${cid}/submissions`, { headers });
    submissions.value = s.data.data?.submissions || [];
  } catch (e) {
    flash(e.response?.data?.message || e.message || '加载班级详情失败', true);
  }
};

const selectClass = (id) => {
  if (activeId.value === id) return;
  activeId.value = id;
  filterAssignment.value = null;
};

const switchTab = (key) => {
  tab.value = key;
  if (key !== 'report') filterAssignment.value = null;
};

watch(activeId, loadDetail);
watch(tab, (key) => { if (key === 'report') filterAssignment.value = null; });

onMounted(loadClasses);

// ------------------------------------------------------------ 操作

const createClass = async () => {
  const name = newClassName.value.trim();
  if (!name || creating.value) return;
  creating.value = true;
  try {
    const res = await request.post('/api/class/create', { name }, { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '创建失败');
    newClassName.value = '';
    flash(`班级创建成功，邀请码：${res.data.data.join_code}`);
    await loadClasses();
    activeId.value = res.data.data.id;
  } catch (e) {
    flash(e.response?.data?.message || e.message || '创建班级失败', true);
  } finally {
    creating.value = false;
  }
};

const removeMember = async (student) => {
  if (!window.confirm(`确认把 ${student} 移出班级？该学生的历史提交会保留。`)) return;
  try {
    const res = await request.post(
      `/api/class/${activeId.value}/remove-member`,
      { student },
      { headers: ownerHeader() },
    );
    if (!res.data.success) throw new Error(res.data.message || '操作失败');
    flash(`已把 ${student} 移出班级`);
    await loadDetail();
  } catch (e) {
    flash(e.response?.data?.message || e.message || '移出失败', true);
  }
};

const publishAssignment = async () => {
  if (!draft.title.trim() || publishing.value) return;
  publishing.value = true;
  try {
    const res = await request.post('/api/assignment/create', {
      class_id: activeId.value,
      title: draft.title.trim(),
      requirements: draft.requirements.trim(),
      grade: draft.grade,
      essay_type: draft.essayType,
    }, { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '发布失败');
    draft.title = '';
    draft.requirements = '';
    flash('作文训练已发布，学生可在「我的班级」中看到');
    await loadDetail();
  } catch (e) {
    flash(e.response?.data?.message || e.message || '发布失败', true);
  } finally {
    publishing.value = false;
  }
};

const deleteAssignment = async (item) => {
  if (!window.confirm(`确认删除《${item.title}》？已提交的批改记录会保留。`)) return;
  try {
    const res = await request.delete(`/api/assignment/${item.id}`, { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '删除失败');
    flash('作业已删除');
    await loadDetail();
  } catch (e) {
    flash(e.response?.data?.message || e.message || '删除失败', true);
  }
};

const openAssignment = async (item) => {
  tab.value = 'report';
  filterAssignment.value = item;
  try {
    const res = await request.get(`/api/assignment/${item.id}/submissions`,
      { headers: ownerHeader() });
    if (res.data.success) missing.value = res.data.data?.missing || [];
  } catch (e) {
    missing.value = [];
  }
};

const viewSubmission = async (item) => {
  viewingLoading.value = true;
  // 先放上列表里的已知信息，详情到了再补全，避免弹层空白
  viewing.value = { ...item, result: null };
  try {
    const res = await request.get(`/api/class/submission/${item.id}`,
      { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '加载失败');
    viewing.value = {
      ...res.data.data,
      owner: item.owner,
      student: item.student,
    };
  } catch (e) {
    flash(e.response?.data?.message || e.message || '加载批改结果失败', true);
    viewing.value = null;
  } finally {
    viewingLoading.value = false;
  }
};
</script>

<style scoped>
.classroom-page { max-width: 960px; margin: 0 auto; padding: 24px 28px 48px; overflow-y: auto; height: 100%; }
.page-head { margin-bottom: 16px; }
.page-title { font-size: var(--fs-xl); font-weight: 700; color: var(--c-text); margin-bottom: 4px; }
.page-sub { font-size: var(--fs-sm); color: var(--c-text-secondary); margin: 0; }

.create-bar { display: flex; gap: 10px; margin-bottom: 12px; }
.create-bar .ui-input { flex: 1; }

.tip { font-size: var(--fs-sm); margin: 0 0 10px; }
.tip--error { color: var(--c-error); }
.tip--ok { color: var(--c-primary); }

.empty { padding: 18px 0; font-size: var(--fs-sm); color: var(--c-text-muted); text-align: center; }
.pane-hint { font-size: var(--fs-xs); color: var(--c-text-muted); margin: 0 0 10px; }

.class-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-bottom: 18px; }
.class-card { display: flex; flex-direction: column; gap: 4px; padding: 14px; font-family: inherit; text-align: left; background: var(--c-surface); border: 1px solid var(--c-border-strong); border-radius: var(--r-lg); cursor: pointer; transition: border-color .15s, box-shadow .15s; }
.class-card:hover { border-color: var(--c-primary); }
.class-card.is-active { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-soft); }
.class-name { font-size: var(--fs-md); font-weight: 600; color: var(--c-text); }
.class-code { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.class-code b { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--c-primary); letter-spacing: 1px; }
.class-meta { font-size: var(--fs-xs); color: var(--c-text-muted); }

.detail { border-top: 1px solid var(--c-border); padding-top: 14px; }
.tabs { display: inline-flex; gap: 0; padding: 3px; background: var(--c-bg-muted); border-radius: var(--r-lg); margin-bottom: 14px; }
.tab { padding: 6px 16px; font-family: inherit; font-size: var(--fs-sm); color: var(--c-text-secondary); background: transparent; border: none; border-radius: var(--r-md); cursor: pointer; }
.tab.is-active { color: var(--c-text); font-weight: 600; background: var(--c-surface); box-shadow: var(--shadow-1); }

.row-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; font-size: var(--fs-sm); background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-md); }
.row-main { font-weight: 600; color: var(--c-text); }
.row-sub { font-size: var(--fs-xs); color: var(--c-text-muted); }
.avatar { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; font-size: 12px; font-weight: 600; color: var(--c-primary); background: var(--c-primary-soft); border-radius: 50%; }
.progress { margin-left: auto; font-size: var(--fs-xs); color: var(--c-text-secondary); }
.score { font-weight: 600; color: var(--c-text); }
.status { font-size: 11px; padding: 2px 8px; border-radius: var(--r-pill); background: var(--c-bg-muted); color: var(--c-text-secondary); }
.status--done { color: #0a7d43; background: #e7f7ee; }
.status--failed { color: var(--c-error); background: #fdecec; }

.form-card { display: flex; flex-direction: column; gap: 8px; padding: 14px; margin-bottom: 14px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); }
.form-row { display: flex; gap: 8px; flex-wrap: wrap; }
.form-row .ui-input { flex: 1; min-width: 140px; }

.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px; }
.stat { display: flex; flex-direction: column; gap: 2px; padding: 12px; text-align: center; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-md); }
.stat b { font-size: var(--fs-lg); color: var(--c-text); }
.stat span { font-size: var(--fs-xs); color: var(--c-text-muted); }

.sub-title { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm); font-weight: 600; color: var(--c-text); margin: 18px 0 8px; }
.filter-tag { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; font-size: 11px; font-weight: 400; color: var(--c-primary); background: var(--c-primary-soft); border-radius: var(--r-pill); }
.filter-tag button { border: none; background: none; color: inherit; cursor: pointer; font-size: 13px; line-height: 1; }

.report-table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.report-table th, .report-table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--c-border); }
.report-table th { font-size: var(--fs-xs); font-weight: 500; color: var(--c-text-secondary); }
.missing { font-size: var(--fs-sm); color: var(--c-text-secondary); }

.modal { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; padding: 24px; background: rgba(9, 17, 53, .45); z-index: 50; }
.modal-card { display: flex; flex-direction: column; width: min(760px, 100%); max-height: 86vh; background: var(--c-surface); border-radius: var(--r-lg); overflow: hidden; }
.modal-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; border-bottom: 1px solid var(--c-border); }
.modal-head h3 { font-size: var(--fs-md); font-weight: 600; margin: 0; }
.modal-close { font-size: 20px; line-height: 1; color: var(--c-text-muted); background: none; border: none; cursor: pointer; }
.modal-body { padding: 16px 18px 20px; overflow-y: auto; }
.modal-score { font-size: var(--fs-sm); color: var(--c-text-secondary); margin: 0 0 10px; }
.modal-score b { font-size: var(--fs-lg); color: var(--c-text); }
.rating { margin-left: 8px; padding: 2px 8px; font-size: 12px; color: var(--c-primary); background: var(--c-primary-soft); border-radius: var(--r-pill); }

.dim-list { list-style: none; margin: 0 0 12px; padding: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.dim-list li { display: flex; justify-content: space-between; padding: 6px 10px; font-size: var(--fs-xs); background: var(--c-bg-muted); border-radius: var(--r-sm); }
.comment { font-size: var(--fs-sm); line-height: 1.8; color: var(--c-text); white-space: pre-wrap; }
.page-img { display: block; width: 100%; margin-top: 12px; border: 1px solid var(--c-border); border-radius: var(--r-md); }
</style>
