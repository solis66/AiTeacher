<template>
  <div class="review-rail">
    <div v-if="loading" class="rail-empty">加载中…</div>
    <div v-else-if="!items.length" class="rail-empty">暂无批改记录</div>

    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      class="rail-item"
      :class="{ 'is-active': item.id === activeId }"
      @click="$emit('select', item.id)"
    >
      <!-- 缩略图 -->
      <div class="rail-thumb">
        <img v-if="item.thumb" :src="fileUrl(item.id, item.thumb)" :alt="item.input?.title || '作文'" />
        <div v-else class="rail-thumb-placeholder"><FileText :size="14" /></div>
      </div>

      <!-- 信息：题目 / 状态 / 分数 / 时间 -->
      <div class="rail-info">
        <span class="rail-name" :title="item.input?.title || '未命名作文'">
          {{ item.input?.title || '未命名作文' }}
        </span>
        <span class="rail-meta">
          <span class="ui-badge" :class="statusClass(item.status)">{{ statusText(item.status) }}</span>
          <span v-if="item.score !== null && item.score !== undefined" class="rail-score">{{ item.score }}分</span>
        </span>
        <span class="rail-time">{{ formatTime(item.created_at) }}</span>
      </div>
    </button>
  </div>
</template>

<script setup>
/**
 * 作文列表（主页面全局侧边栏「批改结果」下的子列表）
 *
 * 位置变更：原先作为批改页内部左栏，现上移到应用外壳的全局侧边栏，
 * 与「批改结果」导航项同列展示，点击即按记录 ID 打开对应批改结果。
 *
 * 显示内容：作文缩略图、题目、批改状态、分数、时间，并标记当前打开的一篇。
 */

import { FileText } from 'lucide-vue-next';
import { reviewPageUrl } from '../../utils/reviewUrl.js';
import { formatRecordTime as formatTime } from '../../utils/format.js';

const props = defineProps({
  items: { type: Array, default: () => [] },
  username: { type: String, default: '' },
  activeId: { type: String, default: null },
  loading: { type: Boolean, default: false }
});

defineEmits(['select']);

// <img> 无法带 X-Username 请求头，缩略图地址必须把 owner 拼进查询参数，否则 404
const fileUrl = (id, name) => reviewPageUrl(id, name, props.username);

const statusText = (status) => ({
  queued: '排队中',
  recognizing: '识别中',
  grading: '批改中',
  done: '已完成',
  failed: '失败'
}[status] || status);

const statusClass = (status) => ({
  queued: 'ui-badge--pending',
  recognizing: 'ui-badge--running',
  grading: 'ui-badge--running',
  done: 'ui-badge--done',
  failed: 'ui-badge--failed'
}[status] || 'ui-badge--muted');
</script>

<style scoped>
.review-rail { display: flex; flex-direction: column; }

.rail-empty { padding: 10px 4px; font-size: var(--fs-xs); color: var(--c-text-muted); }

.rail-item {
  display: flex;
  gap: 7px;
  width: 100%;
  padding: 6px;
  margin-bottom: 4px;
  text-align: left;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-family: inherit;
  transition: border-color .15s, background-color .15s;
}
.rail-item:hover { background: var(--c-bg-subtle); }
/* 当前作文：主色边框 + 左侧色条，标记清晰 */
.rail-item.is-active {
  border-color: var(--c-primary);
  background: var(--c-primary-soft);
  box-shadow: inset 3px 0 0 var(--c-primary);
}

.rail-thumb {
  width: 28px;
  height: 36px;
  flex-shrink: 0;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}
.rail-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.rail-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-muted);
}

.rail-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.rail-name {
  font-size: var(--fs-xs);
  color: var(--c-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rail-meta { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.rail-meta .ui-badge { padding: 0 5px; font-size: 10px; }
.rail-score { font-size: 10px; font-weight: 600; color: var(--c-primary); }
.rail-time { font-size: 10px; color: var(--c-text-muted); }
</style>