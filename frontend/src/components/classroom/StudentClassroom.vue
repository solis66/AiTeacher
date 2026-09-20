<template>
  <section class="classroom-page">
    <header class="page-head">
      <h2 class="page-title">我的班级</h2>
      <p class="page-sub">用老师给的邀请码加入班级，查看作文训练并提交</p>
    </header>

    <!-- 加入班级 -->
    <div class="join-bar">
      <input
        v-model="joinCode"
        class="ui-input code-input"
        placeholder="输入 6 位班级邀请码"
        maxlength="8"
        @keydown.enter="joinClass"
      />
      <button
        type="button"
        class="ui-btn ui-btn--primary"
        :disabled="joining || !joinCode.trim()"
        @click="joinClass"
      >
        <UserPlus :size="14" />
        <span>{{ joining ? '加入中…' : '加入班级' }}</span>
      </button>
    </div>

    <p v-if="error" class="tip tip--error">{{ error }}</p>
    <p v-if="notice" class="tip tip--ok">{{ notice }}</p>

    <!-- 我的班级 -->
    <div v-if="classes.length" class="class-chips">
      <span v-for="c in classes" :key="c.id" class="class-chip">
        <b>{{ c.name }}</b>
        <span>老师：{{ c.teacher }}</span>
        <button type="button" class="chip-remove" title="退出班级" @click="leaveClass(c)">×</button>
      </span>
    </div>

    <h4 class="section-title">作文训练</h4>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!assignments.length" class="empty">
      还没有作文训练。加入班级后，老师发布的作业会显示在这里。
    </div>

    <ul v-else class="assign-list">
      <li v-for="item in assignments" :key="item.id" class="assign-card">
        <div class="assign-head">
          <div class="assign-info">
            <span class="assign-title">{{ item.title }}</span>
            <span class="assign-sub">
              {{ item.class_name }} · 老师 {{ item.teacher }}
              <template v-if="item.grade"> · {{ item.grade }}</template>
            </span>
          </div>
          <span class="assign-state" :class="stateClass(item)">{{ stateLabel(item) }}</span>
        </div>

        <p v-if="item.requirements" class="assign-req">题干要求：{{ item.requirements }}</p>

        <div class="assign-actions">
          <button
            v-if="!item.submitted"
            type="button"
            class="ui-btn ui-btn--primary"
            @click="openSubmit(item)"
          >
            <PenLine :size="14" /><span>写作文并提交</span>
          </button>
          <template v-else>
            <button
              v-if="item.submission?.status === 'done'"
              type="button"
              class="ui-btn ui-btn--ghost"
              @click="emit('open-review', item.submission.review_id)"
            >
              <FileSearch :size="14" /><span>查看批改结果</span>
            </button>
            <span v-else-if="item.submission?.status === 'failed'" class="hint-failed">
              上次批改失败：{{ item.submission.error || '请重试' }}
            </span>
            <span v-else class="hint-wait">批改中，稍后刷新查看…</span>
            <button type="button" class="ui-text-btn" @click="openSubmit(item)">重新提交</button>
          </template>
        </div>

        <!-- 提交面板 -->
        <div v-if="activeId === item.id" class="submit-panel">
          <div class="field">
            <span class="field-label">年级 <em>*</em></span>
            <select v-model="draft.grade" class="ui-input">
              <option value="" disabled>请选择年级</option>
              <option v-for="g in grades" :key="g" :value="g">{{ g }}</option>
            </select>
          </div>
          <div class="field">
            <span class="field-label">作文题目</span>
            <input v-model="draft.title" class="ui-input" maxlength="100" />
          </div>
          <div class="field">
            <span class="field-label">题干要求</span>
            <textarea v-model="draft.requirements" class="ui-textarea" rows="2"></textarea>
          </div>
          <div class="field">
            <span class="field-label">作文正文</span>
            <textarea
              v-model="draft.body"
              class="ui-textarea body-box"
              placeholder="在此输入作文正文，或上传作文图片/PDF"
            ></textarea>
          </div>

          <div class="upload-row">
            <button type="button" class="ui-btn ui-btn--ghost" @click="pickFiles">
              <Upload :size="14" /><span>上传图片 / PDF</span>
            </button>
            <span class="upload-count">{{ draft.files.length }} / 3</span>
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg,.pdf"
              multiple
              class="visually-hidden"
              @change="onFiles"
            />
            <span v-for="(f, i) in draft.files" :key="i" class="file-chip">
              {{ f.name }}
              <button type="button" class="chip-remove" @click="draft.files.splice(i, 1)">×</button>
            </span>
          </div>

          <div class="submit-actions">
            <button
              type="button"
              class="ui-btn ui-btn--primary"
              :disabled="submitting"
              @click="doSubmit"
            >
              <Loader2 v-if="submitting" :size="14" class="spin" />
              <Send v-else :size="14" />
              <span>{{ submitting ? '提交中…' : '提交批改' }}</span>
            </button>
            <button type="button" class="ui-text-btn" @click="closeSubmit">取消</button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
/**
 * 学生端「我的班级」
 *
 * 能力：凭邀请码加入班级 → 查看老师发布的作文训练 → 提交作文（正文或图片）。
 *
 * 提交走的是既有批改流程（POST /api/review），只额外带上 assignment_id；
 * 服务端会校验「我确实在这个班」，并把学生归属强制设成本人账号，
 * 这样老师那边的班级统计口径才是准的。
 */
import { ref, reactive, onMounted } from 'vue';
import { UserPlus, PenLine, FileSearch, Upload, Send, Loader2 } from 'lucide-vue-next';
import request from '../../api/request.js';

const props = defineProps({ username: { type: String, default: '' } });
const emit = defineEmits(['error', 'submitted', 'open-review']);

const grades = ['七年级', '八年级', '九年级'];
const MAX_FILES = 3;

const classes = ref([]);
const assignments = ref([]);
const loading = ref(false);
const joining = ref(false);
const submitting = ref(false);
const joinCode = ref('');
const error = ref('');
const notice = ref('');
const activeId = ref(null);
const fileInput = ref(null);

const draft = reactive({ title: '', requirements: '', grade: '', body: '', files: [] });

const ownerHeader = () => ({ 'X-Username': props.username || 'anonymous' });

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

const stateLabel = (item) => {
  if (!item.submitted) return '未提交';
  const status = item.submission?.status;
  if (status === 'done') return `已完成 ${item.submission.score ?? ''} 分`;
  if (status === 'failed') return '批改失败';
  return '批改中';
};

const stateClass = (item) => {
  if (!item.submitted) return 'state--todo';
  const status = item.submission?.status;
  if (status === 'done') return 'state--done';
  if (status === 'failed') return 'state--failed';
  return 'state--running';
};

// ------------------------------------------------------------ 数据

const loadAll = async () => {
  loading.value = true;
  const headers = ownerHeader();
  try {
    const [c, a] = await Promise.all([
      request.get('/api/class/joined', { headers }),
      request.get('/api/assignment/mine', { headers }),
    ]);
    classes.value = c.data.data || [];
    assignments.value = a.data.data || [];
  } catch (e) {
    flash(e.response?.data?.message || e.message || '加载失败', true);
  } finally {
    loading.value = false;
  }
};

onMounted(loadAll);

// ------------------------------------------------------------ 班级

const joinClass = async () => {
  const code = joinCode.value.trim();
  if (!code || joining.value) return;
  joining.value = true;
  try {
    const res = await request.post('/api/class/join', { join_code: code }, { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '加入失败');
    joinCode.value = '';
    flash(`已加入「${res.data.data.name}」`);
    await loadAll();
  } catch (e) {
    flash(e.response?.data?.message || e.message || '加入班级失败', true);
  } finally {
    joining.value = false;
  }
};

const leaveClass = async (item) => {
  if (!window.confirm(`确认退出「${item.name}」？已提交的作文与批改结果会保留。`)) return;
  try {
    const res = await request.post(`/api/class/${item.id}/leave`, {}, { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '退出失败');
    flash('已退出班级');
    await loadAll();
  } catch (e) {
    flash(e.response?.data?.message || e.message || '退出失败', true);
  }
};

// ------------------------------------------------------------ 提交作文

const openSubmit = (item) => {
  activeId.value = item.id;
  draft.title = item.title || '';
  draft.requirements = item.requirements || '';
  draft.grade = item.grade || '';
  draft.body = '';
  draft.files = [];
};

const closeSubmit = () => { activeId.value = null; };

const pickFiles = () => fileInput.value?.click();

const onFiles = (event) => {
  const chosen = Array.from(event.target.files || []);
  event.target.value = '';
  for (const file of chosen) {
    if (draft.files.length >= MAX_FILES) {
      flash(`一次最多上传${MAX_FILES}张图片/PDF`, true);
      break;
    }
    if (file.size > 20 * 1024 * 1024) {
      flash('单个文件不能超过20MB', true);
      continue;
    }
    draft.files.push(file);
  }
};

const doSubmit = async () => {
  if (submitting.value) return;
  if (!draft.grade) { flash('请选择年级', true); return; }
  if (!draft.body.trim() && !draft.files.length) {
    flash('请填写作文正文，或上传作文图片/PDF', true);
    return;
  }
  submitting.value = true;
  try {
    const fd = new FormData();
    fd.append('grade', draft.grade);
    fd.append('essay_type', '');
    fd.append('title', draft.title);
    fd.append('requirements', draft.requirements);
    fd.append('body', draft.body);
    fd.append('student', '');
    fd.append('assignment_id', String(activeId.value));
    draft.files.forEach((file) => fd.append('files', file, file.name));

    const res = await request.post('/api/review', fd, { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '提交失败');

    activeId.value = null;
    flash('提交成功，正在批改中…');
    emit('submitted', [res.data.data]);
    await loadAll();
  } catch (e) {
    flash(e.response?.data?.message || e.message || '提交失败', true);
  } finally {
    submitting.value = false;
  }
};
</script>

<style scoped>
.classroom-page { max-width: 860px; margin: 0 auto; padding: 24px 28px 48px; overflow-y: auto; height: 100%; }
.page-head { margin-bottom: 16px; }
.page-title { font-size: var(--fs-xl); font-weight: 700; color: var(--c-text); margin-bottom: 4px; }
.page-sub { font-size: var(--fs-sm); color: var(--c-text-secondary); margin: 0; }

.join-bar { display: flex; gap: 10px; margin-bottom: 12px; }
.code-input { flex: 1; text-transform: uppercase; letter-spacing: 2px; }

.tip { font-size: var(--fs-sm); margin: 0 0 10px; }
.tip--error { color: var(--c-error); }
.tip--ok { color: var(--c-primary); }

.class-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 6px; }
.class-chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; font-size: var(--fs-xs); color: var(--c-text-secondary); background: var(--c-bg-muted); border-radius: var(--r-pill); }
.class-chip b { color: var(--c-text); }
.chip-remove { border: none; background: none; color: var(--c-text-muted); font-size: 14px; line-height: 1; cursor: pointer; }

.section-title { font-size: var(--fs-md); font-weight: 600; color: var(--c-text); margin: 18px 0 10px; }
.empty { padding: 18px 0; font-size: var(--fs-sm); color: var(--c-text-muted); text-align: center; }

.assign-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.assign-card { padding: 16px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); }
.assign-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.assign-info { display: flex; flex-direction: column; gap: 3px; }
.assign-title { font-size: var(--fs-md); font-weight: 600; color: var(--c-text); }
.assign-sub { font-size: var(--fs-xs); color: var(--c-text-muted); }
.assign-state { flex-shrink: 0; padding: 3px 10px; font-size: 12px; border-radius: var(--r-pill); }
.state--todo { color: var(--c-text-secondary); background: var(--c-bg-muted); }
.state--done { color: #0a7d43; background: #e7f7ee; }
.state--failed { color: var(--c-error); background: #fdecec; }
.state--running { color: var(--c-primary); background: var(--c-primary-soft); }
.assign-req { font-size: var(--fs-sm); line-height: 1.7; color: var(--c-text-secondary); margin: 10px 0 0; white-space: pre-wrap; }

.assign-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.hint-failed { font-size: var(--fs-xs); color: var(--c-error); }
.hint-wait { font-size: var(--fs-xs); color: var(--c-text-muted); }

.submit-panel { margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--c-border-strong); display: flex; flex-direction: column; gap: 10px; }
.field { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.field-label em { color: var(--c-error); font-style: normal; }
.body-box { min-height: 130px; line-height: 1.8; }

.upload-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.upload-count { font-size: var(--fs-xs); color: var(--c-text-muted); }
.file-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; font-size: 12px; background: var(--c-bg-muted); border-radius: var(--r-pill); }
.visually-hidden { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }

.submit-actions { display: flex; align-items: center; gap: 12px; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
