<template>
  <aside class="review-rail">
    <header class="rail-head">
      <span class="rail-title">作文列表</span>
      <button type="button" class="ui-icon-btn" data-tip="收起" @click="$emit('close')">
        <PanelLeftClose :size="15" />
      </button>
    </header>

    <div class="rail-list">
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
          <div v-else class="rail-thumb-placeholder"><FileText :size="16" /></div>
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
  </aside>
</template>

<script setup>
/**
 * 批改页左栏：作文列表
 *
 * 需求对应：
 * - 宽度约 200px
 * - 显示作文缩略图、批改状态、分数和时间
 * - 清晰标记当前作文
 * - 支持通过历史记录 ID 再次打开（点击列表项即按 ID 加载）
 */

import { FileText, PanelLeftClose } from 'lucide-vue-next';
import { reviewPageUrl } from '../../utils/reviewUrl.js';

const props = defineProps({
  items: { type: Array, default: () => [] },
  username: { type: String, default: '' },
  activeId: { type: String, default: null },
  loading: { type: Boolean, default: false }
});

defineEmits(['select', 'close']);

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

const formatTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
</script>

<style scoped>
.review-rail {
  display: flex;
  flex-direction: column;
  width: var(--rail-width);
  flex-shrink: 0;
  background: var(--c-bg);
  border-right: 1px solid var(--c-border);
  min-height: 0;
}

.rail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--topbar-height);
  padding: 0 8px 0 12px;
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.rail-title { font-size: var(--fs-sm); font-weight: 600; color: var(--c-text-secondary); }

.rail-list { flex: 1; overflow-y: auto; padding: 8px; }

.rail-empty { padding: 24px 8px; text-align: center; font-size: var(--fs-xs); color: var(--c-text-muted); }

.rail-item {
  display: flex;
  gap: 8px;
  width: 100%;
  padding: 8px;
  margin-bottom: 6px;
  text-align: left;
  background: var(--c-bg);
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
  width: 34px;
  height: 44px;
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

.rail-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.rail-name {
  font-size: var(--fs-xs);
  color: var(--c-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rail-meta { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
.rail-meta .ui-badge { padding: 0 6px; font-size: 10px; }
.rail-score { font-size: 11px; font-weight: 600; color: var(--c-primary); }
.rail-time { font-size: 10px; color: var(--c-text-muted); }
</style>
