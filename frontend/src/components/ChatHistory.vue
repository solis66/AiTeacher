<template>
  <div class="chat-history" ref="chatHistoryRef">
    <div
      v-for="(msg, index) in messages"
      :key="msg.id || index"
      class="message"
      :class="{ 'user': msg.role === 'user', 'assistant': msg.role === 'assistant' }"
    >
      <!-- 头像 -->
      <div class="message-avatar">
        <User v-if="msg.role === 'user'" :size="16" />
        <Bot v-else :size="16" />
      </div>

      <div class="message-content-wrapper">
        <div class="message-header">
          <span class="message-role">{{ msg.role === 'user' ? '我' : 'AI批改老师' }}</span>
          <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
        </div>

        <!-- ============ 用户消息 ============ -->
        <template v-if="msg.role === 'user'">
          <!-- 命题信息：与正文区分展示 -->
          <div v-if="msg.essayType || msg.grade || msg.title" class="user-meta">
            <span v-if="msg.grade" class="ui-badge ui-badge--muted">{{ msg.grade }}</span>
            <span v-if="msg.essayType" class="ui-badge ui-badge--muted">{{ msg.essayType }}</span>
            <span v-if="msg.title" class="user-title">《{{ msg.title }}》</span>
            <span v-if="msg.requirements" class="user-req">要求：{{ msg.requirements }}</span>
          </div>

          <div v-if="msg.content" class="message-content">{{ msg.content }}</div>

          <!-- 附件缩略图（点击可全屏预览） -->
          <div v-if="msg.attachments && msg.attachments.length" class="user-attachments">
            <button
              v-for="(att, ai) in msg.attachments"
              :key="ai"
              type="button"
              class="user-attachment"
              @click="att.kind === 'image' && att.url && previewImage(att.url)"
            >
              <img v-if="att.kind === 'image' && att.url" :src="att.url" :alt="att.name" />
              <div v-else class="user-attachment-file">
                <FileText :size="16" />
                <span>PDF</span>
              </div>
              <span class="user-attachment-name">{{ att.name }}</span>
            </button>
          </div>
        </template>

        <!-- ============ AI：批改中 ============ -->
        <div v-else-if="msg.type === 'review_pending'" class="message-content review-pending">
          <Loader2 :size="16" class="spin" />
          <span>你的ai老师正在批改中...</span>
        </div>

        <!-- ============ AI：批改完成入口（不在对话中展开报告） ============ -->
        <div v-else-if="msg.type === 'review_entry'" class="message-content review-entry">
          <button type="button" class="entry-card" @click="openReview(msg.reviewId)">
            <!-- 带批注的作文缩略图：图片 + 波浪线/圈画标记 -->
            <div class="entry-thumb">
              <img v-if="entryThumb(msg)" :src="entryThumb(msg)" alt="批改后的作文" />
              <div v-else class="entry-thumb-placeholder"><FileText :size="22" /></div>
              <svg class="entry-marks" viewBox="0 0 60 76" preserveAspectRatio="none" aria-hidden="true">
                <path d="M8 20 q4 -3 8 0 t8 0 t8 0" stroke="#d93025" stroke-width="1.2" fill="none" />
                <path d="M8 42 q4 -3 8 0 t8 0" stroke="#d93025" stroke-width="1.2" fill="none" />
                <circle cx="44" cy="56" r="5" stroke="#188038" stroke-width="1.2" fill="none" />
              </svg>
            </div>
            <div class="entry-body">
              <span class="entry-title">批改完成，点击查看批改详情</span>
              <span class="entry-sub">
                {{ msg.essayType || '作文' }}
                <template v-if="msg.score !== null && msg.score !== undefined">
                  · {{ msg.score }}分（{{ msg.rating || '' }}）
                </template>
                <template v-if="msg.pageCount"> · 共{{ msg.pageCount }}页</template>
              </span>
            </div>
            <ChevronRight :size="18" class="entry-arrow" />
          </button>
        </div>

        <!-- ============ AI：批改失败（给出原因与重试，不伪造结果） ============ -->
        <div v-else-if="msg.type === 'review_failed'" class="message-content review-failed">
          <div class="failed-head">
            <AlertCircle :size="16" />
            <span>批改失败</span>
          </div>
          <p class="failed-reason">{{ msg.error || '未知错误' }}</p>
          <div class="failed-actions">
            <button v-if="msg.reviewId" type="button" class="ui-btn" @click="retryReview(msg.reviewId)">
              <RefreshCw :size="14" /><span>重试</span>
            </button>
            <span class="failed-hint">重试将复用已上传的作文材料</span>
          </div>
        </div>

        <!-- ============ AI：普通回复（咨询类） ============ -->
        <div v-else class="message-content">{{ msg.content }}</div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="messages.length === 0" class="empty-state">
      <div class="empty-icon"><FileText :size="40" /></div>
      <div class="empty-title">开始你的作文批改之旅</div>
      <div class="empty-desc">
        输入作文正文，或上传作文图片 / PDF（一次上传视为同一篇作文，最多3张），选择年级后发送，AI 批改老师将为你批改
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 对话历史组件
 *
 * 本次变更（对应需求「三、对话中的批改状态」）：
 * 1. 提交后显示加载图标 +「你的ai老师正在批改中...」。
 * 2. 完成后只显示**简洁的批改入口卡**（带批注的作文缩略图），点击进入批改页；
 *    不再在对话中展开完整报告。
 * 3. 失败时显示真实错误原因与重试按钮，不生成虚假的完成结果。
 * 4. 用户消息展示体裁/年级/题目/题干要求与附件缩略图，便于返回首页后继续查看。
 *
 * @props messages 消息列表
 * @event preview-image / open-review / retry-review
 */

import { ref, watch, nextTick } from 'vue';
import { FileText, ChevronRight, Loader2, AlertCircle, RefreshCw, User, Bot } from 'lucide-vue-next';
import { reviewPageUrl } from '../utils/reviewUrl.js';
import { formatChatTime as formatTime } from '../utils/format.js';

const props = defineProps({
  messages: { type: Array, default: () => [] },
  username: { type: String, default: '' }
});

const emit = defineEmits(['preview-image', 'open-review', 'retry-review']);

const chatHistoryRef = ref(null);

/**
 * 入口卡缩略图地址在渲染时现算，不直接用消息里存下的 thumbUrl。
 *
 * 原因：消息会被序列化进 localStorage，而缩略图地址需要带 owner 查询参数
 * （<img> 无法携带 X-Username 请求头）。若沿用历史记录里存下的旧地址，
 * 恢复旧会话时会因为缺少 owner 而 404。
 */
const entryThumb = (msg) => {
  if (!msg || !msg.reviewId) return '';
  const file = msg.thumb || 'page-1.jpg';
  return reviewPageUrl(msg.reviewId, file, props.username);
};

const previewImage = (url) => emit('preview-image', url);
const openReview = (id) => id && emit('open-review', id);
const retryReview = (id) => id && emit('retry-review', id);

/** 新消息到达后滚动到底部 */
const scrollToBottom = async () => {
  await nextTick();
  if (chatHistoryRef.value) chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight;
};

watch(() => props.messages.length, scrollToBottom);
</script>

<style scoped>
.chat-history {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  scroll-behavior: smooth;
}

.message { display: flex; gap: 12px; max-width: 76%; margin-bottom: 16px; }
.message.user { margin-left: auto; margin-right: 0; }
.message.assistant { margin-left: 0; margin-right: auto; }

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: var(--c-bg-muted);
  color: var(--c-text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.message.user .message-avatar { background-color: var(--c-primary); color: #fff; }

.message-content-wrapper { flex: 1; min-width: 0; }

.message-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.message-role { font-size: var(--fs-xs); font-weight: 600; color: var(--c-text-secondary); }
.message-time { font-size: 11px; color: var(--c-text-muted); }

.message-content {
  padding: 10px 14px;
  border-radius: var(--r-md);
  font-size: var(--fs-md);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.message.user .message-content { background-color: var(--c-primary-soft); }
.message.assistant .message-content { background-color: var(--c-surface); border: 1px solid var(--c-border); }

/* 命题信息 */
.user-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
}
.user-title { font-weight: 600; color: var(--c-text); }
.user-req { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 用户附件 */
.user-attachments { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.user-attachment {
  position: relative;
  width: 96px;
  padding: 0;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  overflow: hidden;
  cursor: pointer;
  transition: border-color .15s;
}
.user-attachment:hover { border-color: var(--c-border-strong); }
.user-attachment img { width: 100%; height: 72px; object-fit: cover; display: block; }
.user-attachment-file {
  height: 72px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  font-size: 11px;
  color: var(--c-text-secondary);
}
.user-attachment-name {
  display: block;
  padding: 3px 6px;
  font-size: 11px;
  color: var(--c-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 批改中 */
.review-pending {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--c-text-secondary);
}
.spin { animation: spin 1s linear infinite; color: var(--c-primary); }
@keyframes spin { to { transform: rotate(360deg); } }

/* 批改入口卡 */
.review-entry { padding: 0; background: transparent; border: none; }
.entry-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
  font-family: inherit;
}
.entry-card:hover { border-color: var(--c-primary); box-shadow: var(--shadow-1); }

.entry-thumb {
  position: relative;
  width: 60px;
  height: 76px;
  flex-shrink: 0;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  overflow: hidden;
  background: var(--c-surface);
}
.entry-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.entry-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-muted);
}
/* 叠加的批注视觉：波浪线 + 圈画，直观表达“已批改” */
.entry-marks { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }

.entry-body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.entry-title { font-size: var(--fs-md); font-weight: 600; color: var(--c-text); }
.entry-sub { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.entry-arrow { color: var(--c-text-muted); flex-shrink: 0; }

/* 批改失败 */
.review-failed {
  background-color: var(--c-error-soft);
  border: 1px solid rgba(217, 48, 37, 0.14);
}
.failed-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-error);
}
.failed-reason { margin: 6px 0 10px; font-size: var(--fs-sm); color: var(--c-text-secondary); line-height: 1.6; }
.failed-actions { display: flex; align-items: center; gap: 10px; }
.failed-hint { font-size: 11px; color: var(--c-text-muted); }

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  text-align: center;
}
.empty-icon { color: var(--c-text-muted); margin-bottom: 16px; }
.empty-title { font-size: var(--fs-lg); font-weight: 600; color: var(--c-text); margin-bottom: 10px; }
.empty-desc { font-size: var(--fs-md); color: var(--c-text-secondary); line-height: 1.6; max-width: 420px; }

@media (max-width: 768px) {
  .chat-history { padding: 14px; }
  .message { max-width: 90%; gap: 10px; }
  .message-content { padding: 8px 12px; font-size: var(--fs-sm); }
}
</style>
