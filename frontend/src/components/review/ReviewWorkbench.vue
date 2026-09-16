<template>
  <section class="review-workbench">
    <!-- ==================== 顶部操作栏（固定） ==================== -->
    <header class="ui-topbar">
      <button type="button" class="ui-btn ui-btn--ghost" @click="$emit('back')">
        <ArrowLeft :size="15" /><span>返回首页</span>
      </button>

      <button
        v-if="!railOpen"
        type="button"
        class="ui-icon-btn"
        data-tip="作文列表"
        @click="railOpen = true"
      >
        <PanelLeftOpen :size="16" />
      </button>

      <div class="topbar-title">
        <span class="title-text">{{ record?.input?.title || '作文批改' }}</span>
        <span v-if="record" class="title-meta">
          {{ record.input?.grade }}{{ record.input?.essay_type ? ' · ' + record.input.essay_type : '' }}
        </span>
        <span v-if="record" class="ui-badge" :class="statusClass">{{ statusText }}</span>
      </div>

      <div class="topbar-actions">
        <button type="button" class="ui-btn" :disabled="!canExport" @click="exportAs('pdf')">
          <FileDown :size="14" /><span>导出PDF</span>
        </button>
        <button
          v-if="isNarrow"
          type="button"
          class="ui-icon-btn"
          :class="{ 'is-active': panelOpen }"
          data-tip="评价编辑"
          @click="panelOpen = !panelOpen"
        >
          <PanelRightOpen :size="16" />
        </button>
        <button type="button" class="ui-btn ui-btn--primary" :disabled="!dirty || saving || !canEdit" @click="save">
          <Save :size="14" /><span>{{ saving ? '保存中…' : '保存修改' }}</span>
        </button>
      </div>
    </header>

    <!-- ==================== 三栏主体 ==================== -->
    <div class="workbench-body">
      <!-- 左栏：作文列表 -->
      <ReviewRail
        v-if="railOpen"
        class="rail-slot"
        :items="items"
        :username="username"
        :active-id="record?.id"
        :loading="listLoading"
        @select="loadReview"
        @close="railOpen = false"
      />

      <!-- 中栏：原文与批注 -->
      <div class="center-slot">
        <!-- 未完成/失败时给出明确状态，不展示空白或占位内容 -->
        <div v-if="record && !canEdit" class="center-status">
          <template v-if="status === 'failed'">
            <AlertCircle :size="22" class="status-icon status-icon--error" />
            <p class="status-title">批改失败</p>
            <p class="status-reason">{{ record.error || '未知错误' }}</p>
            <button type="button" class="ui-btn ui-btn--primary" @click="retry">
              <RefreshCw :size="14" /><span>重试</span>
            </button>
          </template>
          <template v-else>
            <Loader2 :size="22" class="status-icon spin" />
            <p class="status-title">你的ai老师正在批改中...</p>
            <p class="status-reason">正在识别原文并生成批改结果，请稍候</p>
          </template>
        </div>

        <ReviewCanvas
          v-else-if="record"
          v-model:page-index="pageIndex"
          :record="record"
          :username="username"
          :zoom="zoom"
          :rotation="rotation"
          :tool="tool"
          :stroke-color="strokeColor"
          :active-annotation="activeAnnotation"
          @add-mark="addMark"
          @erase-marks="eraseMarks"
          @commit-marks="markDirty"
          @select-annotation="activeAnnotation = $event"
          @zoom-delta="(d) => setZoom(zoom + d)"
          @set-zoom="zoom = $event"
        >
          <!-- 底部工具栏：通过插槽渲染在画布（舞台）正下方，宽度仅占画布区域 -->
          <template #toolbar>
            <footer class="ui-toolbar">
              <!-- 工具组：仅保留涂写（画笔）与擦除（橡皮擦） -->
              <button type="button" class="ui-icon-btn" :class="{ 'is-active': tool === 'pen' }" data-tip="画笔" @click="setTool('pen')">
                <Pen :size="16" />
              </button>
              <button type="button" class="ui-icon-btn" :class="{ 'is-active': tool === 'eraser' }" data-tip="橡皮擦" @click="setTool('eraser')">
                <Eraser :size="16" />
              </button>

              <!-- 画笔颜色：画笔工具下可选 -->
              <div v-if="tool !== 'select'" class="tool-options">
                <button
                  v-for="c in colors"
                  :key="c.value"
                  type="button"
                  class="color-dot"
                  :class="{ 'is-active': strokeColor === c.value }"
                  :style="{ background: c.value }"
                  :data-tip="c.label"
                  @click="strokeColor = c.value"
                ></button>
              </div>

              <span class="ui-toolbar__divider"></span>

              <!-- 撤销 / 恢复 -->
              <button type="button" class="ui-icon-btn" data-tip="撤销" :disabled="!undoStack.length" @click="undo">
                <Undo2 :size="16" />
              </button>
              <button type="button" class="ui-icon-btn" data-tip="恢复" :disabled="!redoStack.length" @click="redo">
                <Redo2 :size="16" />
              </button>

              <span class="ui-toolbar__divider"></span>

              <!-- 缩放 / 旋转 -->
              <button type="button" class="ui-icon-btn" data-tip="缩小" @click="setZoom(zoom - 0.15)">
                <ZoomOut :size="16" />
              </button>
              <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
              <button type="button" class="ui-icon-btn" data-tip="放大" @click="setZoom(zoom + 0.15)">
                <ZoomIn :size="16" />
              </button>
              <button type="button" class="ui-icon-btn" data-tip="旋转90°" @click="rotate">
                <RotateCw :size="16" />
              </button>
              <button type="button" class="ui-icon-btn" data-tip="重置视图" @click="resetView">
                <Maximize :size="16" />
              </button>

              <span class="ui-toolbar__divider"></span>

              <!-- 翻页 / 当前页下载 -->
              <button type="button" class="ui-icon-btn" data-tip="上一页" :disabled="pageIndex <= 0" @click="pageIndex -= 1">
                <ChevronLeft :size="16" />
              </button>
              <span class="page-value">{{ pageIndex + 1 }} / {{ pageCount }}</span>
              <button type="button" class="ui-icon-btn" data-tip="下一页" :disabled="pageIndex >= pageCount - 1" @click="pageIndex += 1">
                <ChevronRight :size="16" />
              </button>
              <button type="button" class="ui-icon-btn" data-tip="下载当前页" :disabled="!pageCount" @click="downloadCurrentPage">
                <Download :size="16" />
              </button>

              <!-- 右侧：保存状态 -->
              <div class="toolbar-right">
                <span v-if="dirty" class="dirty-flag">有未保存的修改</span>
                <span v-else-if="lastSavedAt" class="dirty-flag muted">已保存 {{ lastSavedAt }}</span>
              </div>
            </footer>
          </template>
        </ReviewCanvas>
      </div>

      <!-- 右栏：评价编辑 -->
      <ReviewPanel
        v-if="record && canEdit && (!isNarrow || panelOpen)"
        class="panel-slot"
        :result="record.result"
        @open-diff="showDiff = true"
        @change="markDirty"
        @notify="notify"
      />
    </div>

    <!-- 润色对比弹窗 -->
    <PolishDiff
      v-if="showDiff && record?.result"
      :original="originalText"
      :polished-title="record.result.polished_title || ''"
      :polished-text="record.result.polished_text || ''"
      @close="showDiff = false"
    />

    <!-- 轻提示 -->
    <div v-if="toast" class="wb-toast">{{ toast }}</div>
  </section>
</template>

<script setup>
/**
 * 作文批改工作台（独立批改结果页）
 *
 * 需求对应：
 * - 三栏结构：左栏约 200px 作文列表、中栏原文与批注自适应、右栏 360–400px 评价编辑
 * - 顶部操作栏固定（返回首页 / 导出 PDF / 保存修改）
 * - 各区域独立滚动
 * - 画布底栏工具：画笔（涂写）、橡皮擦（擦除）、颜色、撤销/恢复、缩放、旋转、翻页、当前页下载；
 *   工具栏渲染在画布（舞台）正下方，宽度仅占画布区域
 * - 窄屏：左右侧栏改为可收起面板，优先保留原文阅读空间
 * - 保存覆盖评分、评语、详细点评、润色稿与手工批注；导出使用已保存版本
 */

import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import request from '../../api/request.js';
import {
  ArrowLeft, PanelLeftOpen, PanelRightOpen, FileDown, Save,
  Pen, Eraser, Undo2, Redo2,
  ZoomIn, ZoomOut, RotateCw, Maximize, ChevronLeft, ChevronRight, Download,
  Loader2, AlertCircle, RefreshCw
} from 'lucide-vue-next';

import ReviewRail from './ReviewRail.vue';
import ReviewCanvas from './ReviewCanvas.vue';
import ReviewPanel from './ReviewPanel.vue';
import PolishDiff from './PolishDiff.vue';

const props = defineProps({
  reviewId: { type: String, default: null },
  username: { type: String, default: '' }
});

defineEmits(['back']);

// ---------------- 数据状态 ----------------
const items = ref([]);
const listLoading = ref(false);
const record = ref(null);
const loading = ref(false);

// ---------------- 编辑状态 ----------------
const dirty = ref(false);
const saving = ref(false);
const lastSavedAt = ref('');

// ---------------- 视图状态 ----------------
const isNarrow = ref(false);
const railOpen = ref(true);
const panelOpen = ref(false);
const pageIndex = ref(0);
const zoom = ref(1);
const rotation = ref(0);
const activeAnnotation = ref(null);
const showDiff = ref(false);
const toast = ref('');

// ---------------- 批注工具状态 ----------------
const tool = ref('select');
const strokeColor = ref('#d93025');
const undoStack = ref([]);
const redoStack = ref([]);

const colors = [
  { value: '#d93025', label: '红色（纠错）' },
  { value: '#188038', label: '绿色（标记）' },
  { value: '#202124', label: '黑色（批注）' }
];

const ownerHeader = () => ({ 'X-Username': props.username || 'anonymous' });

// ---------------- 计算属性 ----------------
const status = computed(() => record.value?.status || 'queued');
const statusText = computed(() => ({
  queued: '排队中', recognizing: '识别中', grading: '批改中', done: '已完成', failed: '失败'
}[status.value] || status.value));
const statusClass = computed(() => ({
  queued: 'ui-badge--pending', recognizing: 'ui-badge--running', grading: 'ui-badge--running',
  done: 'ui-badge--done', failed: 'ui-badge--failed'
}[status.value] || 'ui-badge--muted'));

const canEdit = computed(() => status.value === 'done' && !!record.value?.result);
const canExport = computed(() => canEdit.value);
const pageCount = computed(() => record.value?.pages?.length || 0);

/** 润色对比的“原文”：优先使用用户输入的正文，否则合并各页识别文本 */
const originalText = computed(() => {
  const body = record.value?.input?.body;
  if (body && body.trim()) return body;
  return (record.value?.pages || []).map((p) => p.text).join('\n');
});

// ---------------- 提示 ----------------
const notify = (message) => {
  toast.value = message;
  setTimeout(() => { toast.value = ''; }, 2200);
};

// ---------------- 数据加载 ----------------
const fetchList = async () => {
  listLoading.value = true;
  try {
    const res = await request.get('/api/review/list', { headers: ownerHeader() });
    if (res.data.success) items.value = res.data.data;
  } catch (e) {
    notify('批改列表加载失败');
  } finally {
    listLoading.value = false;
  }
};

const loadReview = async (id) => {
  if (!id) return;
  loading.value = true;
  try {
    const res = await request.get(`/api/review/${id}`, { headers: ownerHeader() });
    if (res.data.success) {
      record.value = res.data.data;
      // 保证手工批注字段存在，避免子组件判空
      if (!record.value.marks) record.value.marks = [];
      pageIndex.value = 0;
      rotation.value = 0;
      dirty.value = false;
      undoStack.value = [];
      redoStack.value = [];
      activeAnnotation.value = null;
      if (isNarrow.value) railOpen.value = false;
    } else {
      notify(res.data.message || '记录加载失败');
    }
  } catch (e) {
    notify(e.response?.data?.message || '记录加载失败');
  } finally {
    loading.value = false;
  }
};

// ---------------- 手工批注与撤销/恢复 ----------------
const uid = () => `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

/** 每次改动前压栈，保证撤销能回到修改之前的状态 */
const pushHistory = () => {
  undoStack.value.push(JSON.stringify(record.value?.marks || []));
  if (undoStack.value.length > 50) undoStack.value.shift();
  redoStack.value = [];
};

const addMark = (mark) => {
  if (!record.value) return;
  pushHistory();
  record.value.marks.push({ id: uid(), ...mark });
  markDirty();
};

const eraseMarks = (ids) => {
  if (!record.value || !ids?.length) return;
  pushHistory();
  record.value.marks = record.value.marks.filter((m) => !ids.includes(m.id));
  markDirty();
};

const undo = () => {
  if (!undoStack.value.length || !record.value) return;
  redoStack.value.push(JSON.stringify(record.value.marks));
  record.value.marks = JSON.parse(undoStack.value.pop());
  markDirty();
};

const redo = () => {
  if (!redoStack.value.length || !record.value) return;
  undoStack.value.push(JSON.stringify(record.value.marks));
  record.value.marks = JSON.parse(redoStack.value.pop());
  markDirty();
};

const markDirty = () => { dirty.value = true; };

// ---------------- 视图操作 ----------------
const setTool = (name) => {
  tool.value = tool.value === name ? 'select' : name;
};
const setZoom = (value) => {
  zoom.value = Math.min(3, Math.max(0.4, Number(value.toFixed(2))));
};
const rotate = () => { rotation.value = (rotation.value + 90) % 360; };
const resetView = () => { zoom.value = 1; rotation.value = 0; };

const downloadCurrentPage = () => {
  const page = record.value?.pages?.[pageIndex.value];
  if (!page) return;
  // 通过 fetch + blob 下载，保证带上下载文件名
  request.get(`/api/review/${record.value.id}/page/${page.file}`, {
    headers: ownerHeader(), responseType: 'blob'
  }).then((res) => {
    const url = URL.createObjectURL(res.data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${record.value.input?.title || '作文'}-第${pageIndex.value + 1}页.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }).catch(() => notify('下载失败'));
};

/** 导出：使用已保存版本（未保存的临时修改不参与导出） */
const exportAs = async (format) => {
  if (dirty.value) {
    notify('请先保存修改，再导出');
    return;
  }
  try {
    const res = await request.get(`/api/review/${record.value.id}/export`, {
      headers: ownerHeader(), params: { format }, responseType: 'blob'
    });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ai批改结果.${format}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    notify(`导出失败：${e.response?.data?.message || e.message}`);
  }
};

/** 保存：覆盖评分、评语、详细点评、润色稿与手工批注 */
const save = async () => {
  if (!record.value || saving.value) return;
  saving.value = true;
  try {
    const r = record.value.result;
    const res = await request.post(`/api/review/${record.value.id}/save`, {
      version: record.value.version,
      score: r.score,
      rating: r.rating,
      overall_comment: r.overall_comment,
      dimensions: r.dimensions,
      rewrites: r.rewrites,
      corrections: r.corrections,
      analysis: r.analysis,
      highlights: r.highlights,
      suggestions: r.suggestions,
      polished_title: r.polished_title,
      polished_text: r.polished_text,
      marks: record.value.marks
    }, { headers: ownerHeader() });

    if (res.data.success) {
      dirty.value = false;
      lastSavedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
      // 保存后回写版本号，避免下一次保存被乐观锁拒绝
      record.value.version = res.data.data.version;
      notify('已保存');
    } else {
      notify(res.data.message || '保存失败');
    }
  } catch (e) {
    notify(e.response?.data?.message || '保存失败，请稍后重试');
  } finally {
    saving.value = false;
  }
};

const retry = async () => {
  try {
    await request.post(`/api/review/${record.value.id}/retry`, {}, { headers: ownerHeader() });
    await loadReview(record.value.id);
    startPolling();
  } catch (e) {
    notify(e.response?.data?.message || '重试失败');
  }
};

// 未完成时轮询，直到出结果（避免用户停在“批改中”不动）
let pollTimer = null;
const startPolling = () => {
  stopPolling();
  pollTimer = setInterval(async () => {
    if (!record.value) return;
    try {
      const res = await request.get(`/api/review/${record.value.id}`, { headers: ownerHeader() });
      if (res.data.success && res.data.data.status !== record.value.status) {
        const keepMarks = record.value.marks;
        record.value = { ...res.data.data, marks: res.data.data.marks?.length ? res.data.data.marks : keepMarks || [] };
        if (record.value.status === 'done' || record.value.status === 'failed') {
          stopPolling();
          fetchList();
        }
      }
    } catch (e) { /* 轮询期间静默重试 */ }
  }, 3000);
};
const stopPolling = () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } };

// ---------------- 生命周期 ----------------
const handleResize = () => {
  const narrow = window.innerWidth < 1280;
  if (narrow !== isNarrow.value) {
    isNarrow.value = narrow;
    // 窄屏收起两侧面板让位原文；宽屏展开左栏，仍可手动收起
    railOpen.value = !narrow;
    panelOpen.value = false;
  }
};

onMounted(async () => {
  handleResize();
  window.addEventListener('resize', handleResize);
  await fetchList();
  const target = props.reviewId || items.value[0]?.id;
  if (target) await loadReview(target);
  if (record.value && !canEdit.value) startPolling();
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  stopPolling();
});

// 外部要求切换作文（例如从历史记录 ID 再次打开）
watch(() => props.reviewId, (id) => { if (id && id !== record.value?.id) loadReview(id); });

// 加载完成后若仍在处理中，自动开始轮询
watch(status, (value) => {
  if (value === 'done' || value === 'failed') stopPolling();
  else startPolling();
});

// 离开前提醒未保存
const beforeUnload = (e) => {
  if (dirty.value) {
    e.preventDefault();
    e.returnValue = '';
  }
};
onMounted(() => window.addEventListener('beforeunload', beforeUnload));
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload));
</script>

<style scoped>
.review-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--c-bg);
}

.ui-topbar { justify-content: flex-start; }

.topbar-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin-left: 4px;
}
.title-text {
  font-size: var(--fs-md);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}
.title-meta { font-size: var(--fs-xs); color: var(--c-text-muted); white-space: nowrap; }

.topbar-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }

.workbench-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.center-slot {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

/* 未完成/失败状态：中栏居中展示明确状态 */
.center-status {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  text-align: center;
}
.status-icon { color: var(--c-primary); }
.status-icon--error { color: var(--c-error); }
.status-title { font-size: var(--fs-lg); font-weight: 600; margin: 0; }
.status-reason { font-size: var(--fs-sm); color: var(--c-text-secondary); margin: 0 0 6px; max-width: 460px; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 底栏二级选项 */
.tool-options {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 6px;
  padding-left: 8px;
  border-left: 1px dashed var(--c-border);
}
.tool-options .ui-chip { height: 24px; font-size: var(--fs-xs); }

.color-dot {
  position: relative;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
}
.color-dot.is-active { border-color: var(--c-text-secondary); }
.color-dot[data-tip]::after {
  content: attr(data-tip);
  position: absolute;
  left: 50%;
  top: calc(100% + 6px);
  transform: translateX(-50%);
  padding: 3px 8px;
  font-size: var(--fs-xs);
  color: #fff;
  background: rgba(32, 33, 36, .92);
  border-radius: var(--r-sm);
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity .12s;
  z-index: 60;
}
.color-dot[data-tip]:hover::after { opacity: 1; }

.zoom-value,
.page-value {
  min-width: 44px;
  text-align: center;
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
}

.toolbar-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.dirty-flag { font-size: var(--fs-xs); color: var(--c-del); }
.dirty-flag.muted { color: var(--c-text-muted); }

.wb-toast {
  position: fixed;
  left: 50%;
  bottom: 72px;
  transform: translateX(-50%);
  padding: 7px 16px;
  font-size: var(--fs-sm);
  color: #fff;
  background: rgba(32, 33, 36, .88);
  border-radius: var(--r-pill);
  z-index: 4000;
}

/* 窄屏：左栏改为覆盖式抽屉，右栏同样覆盖，优先保留原文阅读空间 */
@media (max-width: 1280px) {
  .rail-slot {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 30;
    box-shadow: var(--shadow-2);
  }
  .panel-slot {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 30;
    box-shadow: var(--shadow-2);
  }
  .workbench-body { position: relative; }
}
</style>
