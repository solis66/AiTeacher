<template>
  <div class="app-shell">
    <!-- ===================== 顶部导航栏 ===================== -->
    <header class="app-navbar">
      <div class="navbar-brand">
        <span class="brand-logo"><GraduationCap :size="20" /></span>
        <span class="brand-name">AI智能批改教师</span>
      </div>

      <div class="navbar-user">
        <span class="user-avatar">{{ currentUser?.charAt(0).toUpperCase() || 'U' }}</span>
        <span class="user-name">{{ currentUser || '用户' }}</span>
        <button type="button" class="logout-btn" @click="handleLogout">退出</button>
      </div>
    </header>

    <div class="app-body">
      <!-- ===================== 左侧边栏 ===================== -->
      <aside class="app-sidebar">
        <nav class="sidebar-nav" aria-label="功能导航">
          <template v-for="item in navItems" :key="item.key">
            <button
              type="button"
              class="side-btn"
              :class="{ 'is-active': page === item.key }"
              @click="go(item.key)"
            >
              <component :is="item.icon" :size="18" />
              <span>{{ item.label }}</span>
            </button>

            <!-- 批改结果：其下直接展示作文列表 -->
            <ReviewRail
              v-if="item.key === 'results' && page === 'results'"
              class="side-sub"
              :items="reviewItems"
              :username="currentUser"
              :active-id="activeReviewId"
              :loading="reviewListLoading"
              @select="openReview"
            />

            <!-- AI咨询：其下展示新对话入口 + 最近 7 天的会话记录 -->
            <div v-if="item.key === 'consult' && page === 'consult'" class="side-sub">
              <button type="button" class="new-chat-btn" @click="startNewConversation">
                <Plus :size="15" />
                <span>新对话</span>
              </button>

              <div class="history-section">
                <p v-if="sessionsLoading" class="consult-hint">加载中…</p>
                <template v-else-if="sessionGroups.length">
                  <div v-for="group in sessionGroups" :key="group.label" class="history-group">
                    <p class="history-time">{{ group.label }}</p>
                    <button
                      v-for="chat in group.items"
                      :key="chat.session_id"
                      type="button"
                      class="history-item"
                      :class="{ active: chat.session_id === currentSessionId }"
                      :title="`${chat.date} ${chat.time} · ${chat.message_count} 条消息`"
                      @click="openSession(chat)"
                    >
                      <span class="history-item-time">{{ chat.date }} {{ chat.time }}</span>
                      <span class="history-item-title">{{ chat.title }}</span>
                    </button>
                  </div>
                </template>
                <p v-else class="consult-hint">最近 7 天暂无咨询记录</p>
              </div>
            </div>
          </template>
        </nav>
      </aside>

      <!-- ===================== 右侧内容区 ===================== -->
      <main class="app-main">
        <!-- 开始批改 -->
        <ReviewSubmit
          v-if="page === 'submit'"
          :username="currentUser"
          @submitted="handleSubmitted"
          @error="showError"
        />

        <!-- 批改结果 -->
        <ReviewWorkbench
          v-else-if="page === 'results'"
          :review-id="activeReviewId"
          :username="currentUser"
          @back="go('submit')"
          @list="onReviewList"
        />

        <!-- 学情报告 -->
        <LearningReport
          v-else-if="page === 'profile'"
          :username="currentUser"
        />

        <!-- AI 咨询（只读对话，零批改入口；会话列表在全局侧边栏「AI咨询」下） -->
        <section v-else class="consult-page">
          <ChatHistory
            :messages="messages"
            :username="currentUser"
            @preview-image="previewImageFull"
            @open-review="openReview"
          />
          <form class="consult-input" @submit.prevent="handleConsultSend">
            <input
              v-model="inputText"
              class="ui-input consult-text"
              placeholder="请输入与学情、写作方法相关的问题…"
              autocomplete="off"
            />
            <button
              type="submit"
              class="ui-btn ui-btn--primary send-btn"
              :disabled="isLoading || !inputText.trim()"
            >
              <Loader2 v-if="isLoading" :size="15" class="spin" />
              <Send v-else :size="15" />
            </button>
          </form>
        </section>
      </main>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMessage" class="error-toast">
      <span class="error-icon"><AlertCircle :size="16" /></span>
      <span class="error-text">{{ errorMessage }}</span>
      <button class="error-close" @click="errorMessage = ''">×</button>
    </div>

    <!-- 全屏图片预览 -->
    <div v-if="fullscreenImage" class="fullscreen-overlay" @click="closeFullscreenImage">
      <div class="fullscreen-content" @click.stop>
        <img :src="fullscreenImage" alt="全屏预览" class="fullscreen-img" />
        <button class="fullscreen-close" @click="closeFullscreenImage">×</button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 主页面（应用外壳）
 *
 * 需求对应（三：页面布局）：
 * - 顶部导航栏（品牌 + 用户信息）+ 左侧边栏 + 右侧内容区
 * - 页面切换入口只在侧边栏：开始批改 / 批改结果 / 学情报告 / AI咨询，
 *   且「批改结果」下展示作文列表、「AI咨询」下展示会话记录
 * - 仅登录取用；各页之间用本地视图切换，不引入 vue-router
 * - AI咨询页为纯 RAG 咨询对话，不挂任何上传/批改表单（零批改入口）
 */
import { ref, onMounted, reactive, computed } from 'vue';
import {
  Calculator, ClipboardList, BarChart3, MessagesSquare,
  GraduationCap, Send, Loader2, AlertCircle, Plus
} from 'lucide-vue-next';
import request from '../api/request.js';
import { getToken, getUser, clearAuth } from '../utils/auth.js';
import ChatHistory from './ChatHistory.vue';
import ReviewRail from './review/ReviewRail.vue';
import ReviewWorkbench from './review/ReviewWorkbench.vue';
import ReviewSubmit from './review/ReviewSubmit.vue';
import LearningReport from './report/LearningReport.vue';

const emit = defineEmits(['logout']);

const navItems = reactive([
  { key: 'submit', label: '开始批改', icon: Calculator },
  { key: 'results', label: '批改结果', icon: ClipboardList },
  { key: 'profile', label: '学情报告', icon: BarChart3 },
  { key: 'consult', label: 'AI咨询', icon: MessagesSquare },
]);

// ---------------- 认证与全局状态 ----------------
// 直接同步初始化：子组件的 onMounted 早于父组件执行，若等到父组件 onMounted 再赋值，
// 子组件首次请求会带上空的 username（回退成 anonymous），导致接口查不到数据、页面空白
const currentUser = ref(getUser());
// 刷新后恢复上次所在的页面与打开的批改记录（localStorage），而不是每次都回到「开始批改」
const PAGE_KEY = 'ai_teacher_last_page';
const REVIEW_KEY = 'ai_teacher_last_review_id';
const SESSION_KEY = 'ai_teacher_last_session_id';
const VALID_PAGES = ['submit', 'results', 'profile', 'consult'];
const storedPage = localStorage.getItem(PAGE_KEY);
const page = ref(VALID_PAGES.includes(storedPage) ? storedPage : 'submit');
const activeReviewId = ref(localStorage.getItem(REVIEW_KEY) || null);
const fullscreenImage = ref(null);
const errorMessage = ref('');

// ---------------- 批改结果：作文列表（由 ReviewWorkbench 回传，展示在侧边栏） ----------------
const reviewItems = ref([]);
const reviewListLoading = ref(false);
/** 接收批改工作台同步的列表、当前打开的记录与加载状态 */
const onReviewList = (payload) => {
  reviewItems.value = Array.isArray(payload?.items) ? payload.items : [];
  reviewListLoading.value = !!payload?.loading;
  // 工作台自行回退打开的记录（如持久化 ID 已失效）时，同步回 activeReviewId，保证侧边栏高亮一致
  const id = payload?.activeId || null;
  if (id && id !== activeReviewId.value) {
    activeReviewId.value = id;
    localStorage.setItem(REVIEW_KEY, id);
  }
};

// ---------------- AI 咨询会话状态 ----------------
const messages = ref([]);
const inputText = ref('');
const isLoading = ref(false);
// 会话列表（服务端按天存储，仅返回最近 7 天）
const sessions = ref([]);
const sessionsLoading = ref(false);
// 当前打开的会话ID：空串表示「新对话」，首次保存时由服务端生成
const currentSessionId = ref(localStorage.getItem(SESSION_KEY) || '');

const CONSULT_HISTORY_MAX = 6;
// 单次持久化的最大消息条数（与后端 MAX_SESSION_MESSAGES 对齐）
const CONSULT_PERSIST_MAX = 200;

/** 把会话列表按天分组（列表已按时间倒序，同一天的记录天然相邻） */
const sessionGroups = computed(() => {
  const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const namedDays = { [dayKey(today)]: '今天', [dayKey(yesterday)]: '昨天' };

  const groups = [];
  for (const item of sessions.value) {
    const label = namedDays[item.date] || item.date;
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
});

// ---------------- 通用工具 ----------------
const showError = (message) => {
  errorMessage.value = message;
  setTimeout(() => { errorMessage.value = ''; }, 5000);
};

// 统一切换页面并持久化，保证刷新后能回到上次所在页面
const go = (key) => {
  if (!VALID_PAGES.includes(key)) key = 'submit';
  page.value = key;
  localStorage.setItem(PAGE_KEY, key);
};

// ---------------- 视图切换 ----------------
/** 提交成功：跳转到批改结果页并打开最新一条记录 */
const handleSubmitted = (records) => {
  const first = records?.[0];
  if (first?.id) {
    activeReviewId.value = first.id;
    localStorage.setItem(REVIEW_KEY, first.id);
  }
  go('results');
};
/** 从咨询历史点击批改卡片 → 打开对应批改结果 */
const openReview = (reviewId) => {
  if (!reviewId) return;
  activeReviewId.value = reviewId;
  localStorage.setItem(REVIEW_KEY, reviewId);
  go('results');
};

// ---------------- AI 咨询（只读问答，走 /chat） ----------------
const buildConsultationHistory = (currentMessage) => {
  const usable = messages.value.filter((m) => (
    (m.role === 'user' || m.role === 'assistant')
    && typeof m.content === 'string' && m.content.trim()
  ));
  const current = (currentMessage || '').trim();
  if (usable.length && usable[usable.length - 1].content.trim() === current) usable.pop();
  return usable.slice(-CONSULT_HISTORY_MAX).map((m) => ({ role: m.role, content: m.content }));
};

const handleConsultSend = async () => {
  const text = inputText.value.trim();
  if (!text || isLoading.value) return;
  inputText.value = '';
  messages.value.push({ role: 'user', content: text, type: 'normal', timestamp: Date.now() });
  messages.value.push({ role: 'assistant', content: '', type: 'normal', status: 'loading', timestamp: Date.now() });
  // 必须取出数组内的响应式代理再修改：直接改 push 进去的原始对象不会触发 Vue 更新，
  // 流式增量会「一个字都不渲染」，直到整段结束才突然出现
  const pending = messages.value[messages.value.length - 1];
  isLoading.value = true;

  const historyPayload = buildConsultationHistory(text);
  let errorText = '';

  // 认证与数据归属请求头（与 api/request.js 拦截器保持一致）
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${getToken()}`,
    'X-Username': currentUser.value || 'anonymous'
  };

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify({ message: text, type: 'consultation', stream: true, history: historyPayload })
    });

    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('text/event-stream')) {
      // 非流式兜底：后端未按 SSE 返回时，按整段 JSON 处理
      const data = await res.json();
      if (res.ok && data.success) {
        const d = data.data;
        pending.content = d.raw_response || d.overall_comment || '（无回复）';
      } else {
        errorText = data.message || '处理请求失败，请稍后重试。';
      }
    } else {
      // 流式：用 ReadableStream 增量读 SSE，逐块追加到正在输入的回复
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let finished = false;
      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sepIndex;
        while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sepIndex).trim();
          buffer = buffer.slice(sepIndex + 2);
          const payload = /^data:\s*(.*)$/s.exec(frame)?.[1];
          if (!payload) continue;
          try {
            const evt = JSON.parse(payload);
            if (evt.type === 'delta' && evt.content) {
              pending.content += evt.content;
            } else if (evt.type === 'error') {
              errorText = evt.content || '处理请求失败，请稍后重试。';
            } else if (evt.type === 'done') {
              finished = true;
              break;
            }
          } catch (e) { /* 跳过无法解析的帧 */ }
        }
      }
      // 流结束后可能残留半帧，忽略即可（服务端以 done / 连接关闭收尾）
    }
  } catch (error) {
    if (error.name === 'AbortError') return;
    errorText = error.response?.data?.message || error.message || '网络连接失败，请检查后端服务是否启动';
  } finally {
    if (errorText) pending.content = errorText;
    if (!pending.content) pending.content = '（无回复）';
    pending.type = 'normal';
    pending.status = '';
    isLoading.value = false;
    // 问答结束后把最新会话持久化，供下次刷新/咨询恢复
    saveHistoryToServer();
  }
};

// ---------------- 咨询历史持久化（按天/会话存储，跨刷新恢复，且作为 AI 上下文） ----------------
/** 把 messages 裁剪成持久化所需的 {role, content, timestamp} 列表 */
const toPersistedHistory = () => messages.value
  .filter((m) => (m.role === 'user' || m.role === 'assistant')
    && typeof m.content === 'string' && m.content.trim())
  .slice(-CONSULT_PERSIST_MAX)
  .map((m) => ({ role: m.role, content: m.content, timestamp: m.timestamp || null }));

/** 服务端时间字符串（'YYYY-MM-DD HH:MM:SS'）转毫秒时间戳 */
const toTimestamp = (text) => {
  const parsed = Date.parse(String(text || '').replace(' ', 'T'));
  return Number.isNaN(parsed) ? Date.now() : parsed;
};

/** 历史消息 → 会话气泡消息 */
const toBubbles = (list) => (Array.isArray(list) ? list : [])
  .filter((m) => (m.role === 'user' || m.role === 'assistant')
    && typeof m.content === 'string' && m.content.trim())
  .map((m) => ({
    role: m.role,
    content: m.content,
    type: 'normal',
    timestamp: toTimestamp(m.time)
  }));

/** 拉取最近 7 天的会话列表 */
const loadSessions = async () => {
  sessionsLoading.value = true;
  try {
    const res = await request.get('/get_history/list');
    if (res.data?.success && Array.isArray(res.data.sessions)) {
      sessions.value = res.data.sessions;
      return res.data.sessions;
    }
  } catch (error) {
    console.warn('[MainPage] 加载会话列表失败:', error?.message || error);
  } finally {
    sessionsLoading.value = false;
  }
  return [];
};

/** 打开某个历史会话（回填该会话的全部消息） */
const openSession = async (session) => {
  const sessionId = session?.session_id;
  if (!sessionId) return;
  currentSessionId.value = sessionId;
  localStorage.setItem(SESSION_KEY, sessionId);
  messages.value = [];
  try {
    const res = await request.get('/get_history', { params: { session_id: sessionId } });
    if (res.data?.success) messages.value = toBubbles(res.data.history);
  } catch (error) {
    console.warn('[MainPage] 加载会话消息失败:', error?.message || error);
  }
};

/** 开启新对话：清空当前会话，首次提问保存时由服务端生成新会话ID */
const startNewConversation = () => {
  currentSessionId.value = '';
  localStorage.removeItem(SESSION_KEY);
  messages.value = [];
  inputText.value = '';
};

/** 把当前会话全量落盘到服务器（同一天的会话归入同一个 Markdown 文件） */
const saveHistoryToServer = async () => {
  const payload = toPersistedHistory();
  if (!payload.length) return;
  try {
    const res = await request.post('/save_history', {
      session_id: currentSessionId.value || '',
      history: payload
    });
    if (res.data?.success && res.data.session_id) {
      if (res.data.session_id !== currentSessionId.value) {
        currentSessionId.value = res.data.session_id;
        localStorage.setItem(SESSION_KEY, res.data.session_id);
      }
      await loadSessions();
    }
  } catch (error) {
    console.warn('[MainPage] 保存咨询历史失败:', error?.message || error);
  }
};

// ---------------- 登出 ----------------
const handleLogout = () => {
  localStorage.removeItem(PAGE_KEY);
  localStorage.removeItem(REVIEW_KEY);
  localStorage.removeItem(SESSION_KEY);
  clearAuth();
  emit('logout');
};

const previewImageFull = (imageUrl) => { fullscreenImage.value = imageUrl; };
const closeFullscreenImage = () => { fullscreenImage.value = null; };

onMounted(async () => {
  // 先取最近 7 天的会话列表，再打开「上次浏览的会话」；
  // 该会话已被删除或不在展示窗口内时，退回最近一个会话，避免白屏
  const list = await loadSessions();
  const savedSessionId = localStorage.getItem(SESSION_KEY) || '';
  const target = list.find((s) => s.session_id === savedSessionId) || list[0];
  if (target) {
    await openSession(target);
  } else {
    currentSessionId.value = '';
    localStorage.removeItem(SESSION_KEY);
  }
});
</script>

<style scoped>
.app-shell { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

/* 顶部导航栏 */
.app-navbar {
  height: var(--app-navbar-height);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
}
.navbar-brand { display: flex; align-items: center; gap: 8px; font-weight: 700; color: var(--c-text); }
.brand-logo { display: grid; place-items: center; width: 32px; height: 32px; color: #fff; background: var(--c-primary); border-radius: var(--r-md); }
.navbar-user { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.user-avatar { display: grid; place-items: center; width: 28px; height: 28px; font-size: var(--fs-sm); font-weight: 600; color: #fff; background: var(--c-primary); border-radius: 50%; }
.user-name { font-size: var(--fs-sm); color: var(--c-text); }
.logout-btn { padding: 5px 12px; font-family: inherit; font-size: var(--fs-xs); border: 1px solid var(--c-border); border-radius: var(--r-md); background: transparent; color: var(--c-text-secondary); cursor: pointer; }
.logout-btn:hover { color: var(--c-error); border-color: var(--c-error); }

/* 主体：侧边栏 + 内容 */
.app-body { flex: 1; display: flex; min-height: 0; }

.app-sidebar {
  width: var(--app-sidebar-width);
  flex-shrink: 0;
  padding: 12px;
  background: var(--c-bg-subtle);
  border-right: 1px solid var(--c-border);
  overflow-y: auto;
}
.sidebar-nav { display: flex; flex-direction: column; gap: 4px; }
.side-btn {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  font-family: inherit; font-size: var(--fs-md);
  border: none; border-radius: var(--r-md);
  background: transparent; color: var(--c-text-secondary);
  cursor: pointer; text-align: left;
}
.side-btn:hover { color: var(--c-text); background: var(--c-bg-muted); }
.side-btn.is-active { color: var(--c-primary); background: var(--c-primary-soft); font-weight: 600; }

/* 导航项下挂的子列表（作文列表 / 会话记录）：缩进并限制高度，避免挤压其它导航项 */
.side-sub { margin: 2px 0 8px; padding-left: 6px; }
.side-sub .history-section { flex: none; max-height: 46vh; overflow-y: auto; }

.app-main { flex: 1; min-width: 0; min-height: 0; overflow: hidden; }
.app-main > :deep(.consult-page) { height: 100%; display: flex; flex-direction: column; }
.app-main > :deep(.review-workbench) { height: 100%; }
.app-main > :deep(.submit-page),
.app-main > :deep(.report-page) { height: 100%; }

/* AI 咨询：会话列表已移到全局侧边栏，内容区只保留对话与输入框 */
.consult-page { background: var(--c-bg); }
.new-chat-btn {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; padding: 9px 12px; margin-bottom: 8px;
  font-family: inherit; font-size: var(--fs-sm); font-weight: 600;
  color: var(--c-primary); background: var(--c-surface);
  border: 1px solid var(--c-border-strong); border-radius: var(--r-md);
  cursor: pointer; flex-shrink: 0;
}
.new-chat-btn:hover { background: var(--c-primary-soft); border-color: var(--c-primary); }
/* 会话条目：时间戳在上，标题在下 */
.history-item { display: flex; flex-direction: column; gap: 2px; width: 100%; }
.history-item-time {
  font-size: 11px; font-variant-numeric: tabular-nums; color: var(--c-text-muted);
}
.history-item-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-item.active .history-item-time { color: var(--c-primary); }
.consult-hint { padding: 12px 4px; font-size: var(--fs-sm); color: var(--c-text-muted); }

.consult-page :deep(.chat-history) { min-width: 0; }
.consult-input { display: flex; gap: 8px; padding: 12px 16px; background: var(--c-surface); border-top: 1px solid var(--c-border); flex-shrink: 0; }
.consult-text { flex: 1; }
.send-btn { width: 44px; flex-shrink: 0; }

.error-toast {
  position: fixed; left: 50%; bottom: 72px; transform: translateX(-50%);
  display: flex; align-items: center; gap: 8px;
  padding: 9px 16px; font-size: var(--fs-sm); color: #fff;
  background: rgba(32, 33, 36, .9); border-radius: var(--r-pill); z-index: 4000;
}
.error-icon { color: #f5b301; }
.error-close { border: none; background: none; color: #fff; font-size: 16px; cursor: pointer; line-height: 1; }

.fullscreen-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, .75); display: grid; place-items: center; z-index: 5000; }
.fullscreen-content { position: relative; max-width: 90vw; max-height: 90vh; }
.fullscreen-img { max-width: 90vw; max-height: 90vh; border-radius: var(--r-md); }
.fullscreen-close { position: absolute; top: -14px; right: -14px; width: 30px; height: 30px; border: none; border-radius: 50%; background: #fff; font-size: 16px; cursor: pointer; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>