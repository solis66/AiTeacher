<template>
  <div class="main-page" :class="{ 'reviewing': view === 'review' }">
    <!-- ===================== 左侧边栏（批改结果页不显示） ===================== -->
    <div v-if="view === 'chat'" class="sidebar">
      <div class="sidebar-header">
        <h1 class="system-title">AI智能批改教师</h1>
      </div>

      <div class="sidebar-buttons">
        <button class="sidebar-action-btn" @click="newChat">
          <span class="btn-icon">+</span>
          <span class="btn-text">新对话</span>
        </button>
        <button class="sidebar-action-btn" @click="openReviewList">
          <span class="btn-icon">📋</span>
          <span class="btn-text">批改记录</span>
        </button>
        <button class="sidebar-action-btn" @click="syncHistory" :disabled="isSyncing">
          <span class="btn-icon">{{ isSyncing ? '⏳' : '🔄' }}</span>
          <span class="btn-text">{{ isSyncing ? '同步中...' : '同步' }}</span>
        </button>
      </div>

      <div class="history-section">
        <template v-for="(group, date) in groupedHistory" :key="date">
          <div class="history-group">
            <div class="history-time">{{ date }}</div>
            <div
              v-for="chat in group"
              :key="chat.id"
              class="history-item"
              :class="{ 'active': currentChatId === chat.id }"
              @click="loadChat(chat.id)"
            >
              <span class="history-label">{{ historyLabel(chat) }}</span>
            </div>
          </div>
        </template>
      </div>

      <div class="user-info-sidebar">
        <div class="avatar">{{ currentUser?.charAt(0).toUpperCase() || 'U' }}</div>
        <div class="user-details">
          <div class="user-name">{{ currentUser || '用户' }}</div>
          <button class="logout-btn" @click="handleLogout">退出登录</button>
        </div>
      </div>
    </div>

    <!-- ===================== 主内容区 ===================== -->
    <div class="main-content">

      <!-- 视图一：AI 对话首页 -->
      <template v-if="view === 'chat'">
        <ChatHistory
          :messages="messages"
          :username="currentUser"
          @preview-image="previewImageFull"
          @open-review="openReview"
          @retry-review="retryReview"
        />
        <InputArea
          v-model="inputText"
          :grade="selectedGrade"
          :is-loading="isLoading"
          @update:grade="selectGrade"
          @send="handleSend"
          @error="showError"
        />
      </template>

      <!-- 视图二：独立的作文批改结果页 -->
      <ReviewWorkbench
        v-else
        :review-id="activeReviewId"
        :username="currentUser"
        @back="backToChat"
      />
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMessage" class="error-toast">
      <div class="error-content">
        <span class="error-icon">⚠️</span>
        <span class="error-text">{{ errorMessage }}</span>
        <button class="error-close" @click="errorMessage = ''">×</button>
      </div>
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
 * 主页面
 *
 * 本次变更（对应需求「优化首页 AI 对话界面，新增独立的作文批改结果页」）：
 * 1. 新增视图切换：'chat'（对话首页）与 'review'（批改工作台），登录页保持不变。
 *    未引入 vue-router，返回首页时会话、附件与批改入口全部保留。
 * 2. 作文提交改走批改工作台接口（POST /api/review），不再在对话里直接出报告。
 * 3. 提交后轮询批改状态，分别落到「批改中 / 完成入口 / 失败重试」三种消息形态。
 * 4. 咨询类提问仍走原有的 /chat 接口。
 */

import { ref, onMounted, onUnmounted, computed } from 'vue';
import axios from 'axios';
import ChatHistory from './ChatHistory.vue';
import InputArea from './InputArea.vue';
import ReviewWorkbench from './review/ReviewWorkbench.vue';
import { reviewPageUrl } from '../utils/reviewUrl.js';

const emit = defineEmits(['logout']);

// ---------------- 认证与全局状态 ----------------
const currentUser = ref('');
const isSyncing = ref(false);
const fullscreenImage = ref(null);
const errorMessage = ref('');

// ---------------- 视图状态 ----------------
const view = ref('chat');
const activeReviewId = ref(null);

// ---------------- 对话状态 ----------------
const messages = ref([]);
const inputText = ref('');
const isLoading = ref(false);
const chatHistory = ref([]);
const currentChatId = ref(null);
const isCreatingChat = ref(false);

// ---------------- 输入区状态 ----------------
const selectedGrade = ref('');

let dateCheckTimer = null;
let lastCheckedDate = '';
const pollTimers = new Map();   // reviewId -> timer，避免组件销毁后继续轮询

const STORAGE_KEY = 'ai_teacher_chat_history';
const TOKEN_KEY = 'ai_teacher_token';
const MAX_HISTORY = 100;
const MAX_HISTORY_DAYS = 7;
const POLL_INTERVAL = 2500;     // 批改状态轮询间隔（毫秒）
const CONSULT_HISTORY_MAX = 6;  // 咨询时随请求带回的最近消息条数（后端还会再裁剪一次）

const essayKeywords = ['作文', '文章', '写作', 'essay', '作文题', '请批改', '请点评', '写一篇', '写了一篇',
  '字数', '段落', '开头', '结尾', '议论文', '记叙文', '说明文'];
const consultationKeywords = ['如何', '怎么', '怎样', '为什么', '请问', '我想问', '问一下', '咨询',
  '方法', '技巧', '策略', '要点', '建议', '告诉我', '分析一下'];

// ---------------- 历史记录分组 ----------------
const groupedHistory = computed(() => {
  const groups = {};
  chatHistory.value.forEach((chat) => {
    const displayDate = chat.displayDate || formatDate(chat.date);
    if (!groups[displayDate]) groups[displayDate] = [];
    groups[displayDate].push(chat);
  });

  const dateOrder = ['现在', '今天', '昨天'];
  const sortedDates = Object.keys(groups).sort((a, b) => {
    const indexA = dateOrder.indexOf(a);
    const indexB = dateOrder.indexOf(b);
    if (indexA !== -1 && indexB !== -1) return indexA - indexB;
    if (indexA !== -1) return -1;
    if (indexB !== -1) return 1;
    return b.localeCompare(a);
  });

  const sorted = {};
  sortedDates.forEach((date) => { sorted[date] = groups[date]; });
  return sorted;
});

/** 侧边栏历史条目文案：优先显示题目，其次显示正文开头 */
const historyLabel = (chat) => {
  const first = chat.messages?.[0] || {};
  const text = first.title || first.content || '新对话';
  return text.length > 18 ? `${text.slice(0, 18)}...` : text;
};

// ---------------- 通用工具 ----------------
const getToken = () => localStorage.getItem(TOKEN_KEY);

const showError = (message) => {
  errorMessage.value = message;
  setTimeout(() => { errorMessage.value = ''; }, 5000);
};

/**
 * 作文提交判定（仅在用户没有主动选择体裁/年级时作为兜底）
 *
 * 规则：
 *  1. 少于 100 字：不是作文，直接按咨询处理
 *  2. 命中咨询关键词且未命中作文关键词：按咨询处理（避免“我想问…”被误判）
 *  3. 命中作文关键词：按作文处理
 *  4. 都没有：按篇幅判断。原阈值 500 字对初中作文过高——一篇 200 多字的
 *     短文会被误判成咨询，直接送到问答链路。这里降到 200 字。
 */
const isEssaySubmission = (text) => {
  const trimmed = (text || '').trim();
  const len = trimmed.length;
  if (len < 100) return false;

  const hasEssayKeywords = essayKeywords.some((kw) => trimmed.includes(kw));
  const hasConsultKeywords = consultationKeywords.some((kw) => trimmed.includes(kw));

  if (hasConsultKeywords && !hasEssayKeywords) return false;
  if (hasEssayKeywords) return true;
  return len >= 200;
};

// ---------------- 发送流程 ----------------
/**
 * 处理发送
 *
 * 分支：
 *  - 作文（含附件/命题信息/长正文）→ 创建批改任务并轮询
 *  - 其他 → 走咨询问答
 */
const handleSend = async ({ content, grade, title, requirements, attachments }) => {
  const userMessage = (content || '').trim();
  const hasAttachments = (attachments || []).length > 0;
  // 主动选择了年级，或填写了题目/题干，等于明确表示「这次是作文」，不再交给关键词猜测。
  // 提交成功后会把年级清空，避免下一条咨询消息被误判成作文。
  const hasMeta = !!(title || requirements || grade);
  const isEssay = hasAttachments || hasMeta || isEssaySubmission(userMessage);

  if (isEssay) {
    // 年级必须选择后才能提交；体裁已移除，由 AI 依据题干要求判定
    if (!grade) return showError('请先选择年级（七年级、八年级或九年级）');
    if (!userMessage && !hasAttachments) return showError('请填写作文正文，或上传作文图片 / PDF');
  } else if (!userMessage) {
    return showError('请输入内容');
  }

  // 用户消息：正文 + 命题信息 + 附件（保留对象引用，便于批改 ID 回填）
  const userMsg = {
    role: 'user',
    content: userMessage,
    type: isEssay ? 'essay_submission' : 'normal',
    essayType: null,
    grade: isEssay ? grade : null,
    title: isEssay ? title : '',
    requirements: isEssay ? requirements : '',
    attachments: (attachments || []).map((att) => ({ kind: att.kind, name: att.name, url: att.url })),
    timestamp: Date.now()
  };
  messages.value.push(userMsg);

  if (!isEssay) {
    await sendConsultation(userMessage);
    return;
  }
  await submitReview({ userMsg, userMessage, grade, title, requirements, attachments });

  // 年级是一次性表单选择，提交后清空：下一条消息默认按咨询处理，
  // 需要再批改时重新选择即可（否则残存的选择会把咨询问题误送进批改链路）。
  selectedGrade.value = '';
};

/** 提交批改任务并进入轮询 */
const submitReview = async ({ userMsg, userMessage, grade, title, requirements, attachments }) => {
  isLoading.value = true;

  // 先插入“批改中”占位，用户立刻能看到状态
  const pendingMessage = {
    role: 'assistant',
    type: 'review_pending',
    status: 'loading',
    reviewId: null,
    timestamp: Date.now()
  };
  messages.value.push(pendingMessage);

  try {
    const formData = new FormData();
    formData.append('grade', grade);
    formData.append('title', title || '');
    formData.append('requirements', requirements || '');
    formData.append('body', userMessage || '');
    // 按用户在输入区排好的顺序追加附件
    (attachments || []).forEach((att) => formData.append('files', att.file, att.name));

    const response = await axios.post('/api/review', formData, {
      headers: { 'X-Username': currentUser.value || 'anonymous' }
    });

    if (!response.data.success) {
      replaceMessage(pendingMessage, {
        role: 'assistant',
        type: 'review_failed',
        error: response.data.message || '创建批改任务失败',
        timestamp: Date.now()
      });
      return;
    }

    const review = response.data.data;
    // 占位消息绑定批改 ID，后续轮询就地更新
    pendingMessage.reviewId = review.id;
    // 把批改 ID 回填到用户消息，便于返回首页/刷新后仍能取到缩略图与批改入口
    userMsg.reviewId = review.id;

    saveCurrentChat();
    startPolling(review.id, pendingMessage);
  } catch (error) {
    replaceMessage(pendingMessage, {
      role: 'assistant',
      type: 'review_failed',
      error: error.response?.data?.message || '网络连接失败，请检查后端服务是否启动',
      timestamp: Date.now()
    });
  } finally {
    isLoading.value = false;
  }
};

/** 轮询批改状态，直到完成或失败 */
const startPolling = (reviewId, message) => {
  stopPolling(reviewId);
  const tick = async () => {
    try {
      const response = await axios.get(`/api/review/${reviewId}`, {
        headers: { 'X-Username': currentUser.value || 'anonymous' }
      });
      if (!response.data.success) return;
      const data = response.data.data;

      if (data.status === 'done') {
        stopPolling(reviewId);
        replaceMessage(message, {
          role: 'assistant',
          type: 'review_entry',
          reviewId,
          essayType: data.input?.essay_type,
          score: data.score,
          rating: data.rating,
          pageCount: data.page_count,
          // 只存文件名，图片地址在渲染时按 owner 现算（见 ChatHistory.entryThumb）
          thumb: data.thumb || 'page-1.jpg',
          thumbUrl: data.thumb ? reviewPageUrl(reviewId, data.thumb, currentUser.value) : '',
          timestamp: Date.now()
        });
        saveCurrentChat();
      } else if (data.status === 'failed') {
        stopPolling(reviewId);
        replaceMessage(message, {
          role: 'assistant',
          type: 'review_failed',
          reviewId,
          error: data.error || '批改失败，请重试',
          timestamp: Date.now()
        });
        saveCurrentChat();
      }
    } catch (error) {
      // 轮询期间的网络抖动不立即判失败，继续按间隔重试
      console.warn('[批改轮询] 请求失败，稍后重试', error?.message);
    }
  };
  tick();
  pollTimers.set(reviewId, setInterval(tick, POLL_INTERVAL));
};

const stopPolling = (reviewId) => {
  const timer = pollTimers.get(reviewId);
  if (timer) {
    clearInterval(timer);
    pollTimers.delete(reviewId);
  }
};

/** 就地替换消息（保持列表长度与滚动位置稳定） */
const replaceMessage = (target, replacement) => {
  const index = messages.value.indexOf(target);
  if (index !== -1) messages.value[index] = replacement;
};

/** 失败重试：复用已上传材料，只重跑批改 */
const retryReview = async (reviewId) => {
  const message = messages.value.find((m) => m.reviewId === reviewId && m.type === 'review_failed');
  if (!message) return;
  try {
    await axios.post(`/api/review/${reviewId}/retry`, {}, {
      headers: { 'X-Username': currentUser.value || 'anonymous' }
    });
    replaceMessage(message, {
      role: 'assistant',
      type: 'review_pending',
      status: 'loading',
      reviewId,
      timestamp: Date.now()
    });
    startPolling(reviewId, messages.value.find((m) => m.reviewId === reviewId && m.type === 'review_pending'));
    saveCurrentChat();
  } catch (error) {
    showError(error.response?.data?.message || '重试失败，请稍后再试');
  }
};

/** 咨询类对话（沿用原有 /chat 接口） */
/**
 * 对话记忆：取本会话最近若干轮可作为上下文的消息
 *
 * 只收有正文的问答消息：批改中占位、批改卡片、失败提示等没有 content 的消息会被排除。
 * 这是前端的初筛，轮次与长度上限由后端 utils.chat_memory 强制，前端传多也不会生效。
 * 之前 /chat 只发一条 message，模型看不到任何上文，用户追问时无法衔接。
 */
const buildConsultationHistory = (currentMessage) => {
  const usable = messages.value.filter((m) => (
    (m.role === 'user' || m.role === 'assistant')
    && typeof m.content === 'string'
    && m.content.trim()
    && (m.type === 'normal' || m.type === 'essay_submission')
  ));
  // 刚入列、且会单独作为 message 传出的当前提问要剔除，否则模型会看到两遍
  const current = (currentMessage || '').trim();
  if (usable.length && usable[usable.length - 1].content.trim() === current) usable.pop();
  return usable.slice(-CONSULT_HISTORY_MAX).map((m) => ({ role: m.role, content: m.content }));
};

const sendConsultation = async (userMessage) => {
  isLoading.value = true;
  const pending = { role: 'assistant', content: '', type: 'loading', status: 'loading', timestamp: Date.now() };
  messages.value.push(pending);
  try {
    // X-Username 必须带上：后端用 request.headers.get('X-Username') 归属数据，
    // 缺失时全部落到 'anonymous'，记忆和日志都无法按人区分（此前这个请求就漏了）。
    const response = await axios.post(
      '/chat',
      {
        message: userMessage,
        type: 'consultation',
        history: buildConsultationHistory(userMessage)
      },
      { headers: { 'X-Username': currentUser.value || 'anonymous' } }
    );
    if (response.data.success) {
      const data = response.data.data;
      replaceMessage(pending, {
        role: 'assistant',
        content: data.raw_response || data.overall_comment || '',
        type: 'normal',
        timestamp: Date.now()
      });
    } else {
      replaceMessage(pending, {
        role: 'assistant',
        content: response.data.message || '处理请求失败，请稍后重试。',
        type: 'normal',
        timestamp: Date.now()
      });
    }
  } catch (error) {
    replaceMessage(pending, {
      role: 'assistant',
      content: error.response?.data?.message || '网络连接失败，请检查后端服务是否启动',
      type: 'normal',
      timestamp: Date.now()
    });
  } finally {
    isLoading.value = false;
    saveCurrentChat();
  }
};

// ---------------- 视图切换 ----------------
/** 打开批改页（从对话入口或历史记录 ID） */
const openReview = (reviewId) => {
  if (!reviewId) return;
  activeReviewId.value = reviewId;
  view.value = 'review';
};

/** 左侧「批改记录」：直接进入批改工作台（左侧列表可按 ID 再次打开） */
const openReviewList = () => {
  activeReviewId.value = activeReviewId.value || null;
  view.value = 'review';
};

const backToChat = () => {
  view.value = 'chat';
  saveCurrentChat();
};

// ---------------- 会话与历史记录 ----------------
const selectGrade = (grade) => { selectedGrade.value = grade; };

const handleLogout = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem('ai_teacher_user');
  emit('logout');
};

const loadHistoryFromServer = async () => {
  const token = getToken();
  if (!token) return;
  try {
    const response = await axios.get('/get_history', { headers: { Authorization: `Bearer ${token}` } });
    if (response.data.success) {
      const mergedHistory = mergeHistory(response.data.history, loadLocalHistory());
      chatHistory.value = mergedHistory
        .filter((chat) => chat.messages && chat.messages.length > 0 && isDateWithinWeek(chat.date))
        .map((chat) => ({ ...chat, displayDate: formatDate(chat.date), reviewId: findReviewId(chat) }));
      saveLocalHistory(chatHistory.value);

      if (chatHistory.value.length > 0) {
        const lastChat = chatHistory.value[0];
        currentChatId.value = lastChat.id;
        messages.value = hydrateAttachments([...lastChat.messages]);
      } else {
        createNewChat(true);
      }
    }
  } catch (error) {
    console.error('从服务器加载历史记录失败:', error);
    loadLocalHistoryData();
  }
};

const syncHistory = async () => {
  const token = getToken();
  if (!token) return;
  isSyncing.value = true;
  try {
    const historyToSync = chatHistory.value.map((chat) => ({
      id: chat.id, date: chat.date, messages: chat.messages
    }));
    const response = await axios.post('/save_history', { history: historyToSync },
      { headers: { Authorization: `Bearer ${token}` } });
    showError(response.data.success ? '历史记录同步成功' : '同步失败');
  } catch (error) {
    showError('同步失败，请检查网络连接');
  } finally {
    isSyncing.value = false;
  }
};

/** 从消息中提取批改 ID，用于历史条目标记与缩略图恢复 */
const findReviewId = (chat) => {
  const hit = (chat.messages || []).find((m) => m.reviewId);
  return hit ? hit.reviewId : null;
};

/**
 * 历史回填：刷新页面后，附件缩略图通过批改记录的首屏图片恢复，
 * 这样“返回首页后保留附件与批改入口”在重新加载后依然成立。
 */
const hydrateAttachments = (msgs) =>
  msgs.map((msg) => {
    if (msg.role !== 'user' || !msg.reviewId || !msg.attachments?.length) return msg;
    return {
      ...msg,
      // 已落库的图片一律按 reviewId 重新生成地址：消息会写进 localStorage，
      // 里面存的 blob:/旧地址在刷新后必然失效，不能直接复用。
      attachments: msg.attachments.map((att) => (
        att.kind === 'image'
          ? { ...att, url: reviewPageUrl(msg.reviewId, 'page-1.jpg', currentUser.value) }
          : att
      ))
    };
  });

const mergeHistory = (serverHistory, localHistory) => {
  const merged = {};
  localHistory.forEach((chat) => { merged[chat.id] = chat; });
  serverHistory.forEach((chat) => { merged[chat.id] = chat; });
  return Object.values(merged).sort((a, b) => new Date(b.date) - new Date(a.date));
};

const loadLocalHistory = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch (e) {
    return [];
  }
};

const saveLocalHistory = (history) => {
  try {
    const dataToSave = history.map((chat) => ({
      id: chat.id, date: chat.date, messages: chat.messages
    })).filter((chat) => isDateWithinWeek(chat.date)).slice(0, MAX_HISTORY);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
  } catch (e) {
    console.error('保存本地历史记录失败:', e);
  }
};

const loadLocalHistoryData = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      chatHistory.value = JSON.parse(saved)
        .filter((chat) => chat.messages && chat.messages.length > 0 && isDateWithinWeek(chat.date))
        .map((chat) => ({ ...chat, displayDate: formatDate(chat.date), reviewId: findReviewId(chat) }));
    }
  } catch (e) {
    chatHistory.value = [];
  }
};

const generateId = () => Date.now().toString(36) + Math.random().toString(36).substr(2);

const isDateWithinWeek = (dateStr) => {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - MAX_HISTORY_DAYS);
  return date >= weekAgo;
};

const getTodayDate = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const day = now.getDate();
  const yesterday = new Date(year, month, day - 1);
  const pad = (n) => String(n).padStart(2, '0');
  return {
    todayStr: `${year}-${pad(month + 1)}-${pad(day)}`,
    yesterdayStr: `${yesterday.getFullYear()}-${pad(yesterday.getMonth() + 1)}-${pad(yesterday.getDate())}`
  };
};

const formatDate = (dateStr) => {
  const { todayStr, yesterdayStr } = getTodayDate();
  const normalizedDate = normalizeDate(dateStr);
  if (!normalizedDate) return dateStr;
  if (normalizedDate === todayStr) return '今天';
  if (normalizedDate === yesterdayStr) return '昨天';
  const [year, month, day] = normalizedDate.split('-');
  return `${year}/${month}/${day}`;
};

const normalizeDate = (dateStr) => {
  if (!dateStr) return null;
  const trimmed = dateStr.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
  return parseChineseDate(trimmed);
};

const parseChineseDate = (chineseDate) => {
  const monthMap = { '一月': '01', '二月': '02', '三月': '03', '四月': '04', '五月': '05', '六月': '06',
    '七月': '07', '八月': '08', '九月': '09', '十月': '10', '十一月': '11', '十二月': '12' };
  const dayMap = {};
  ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四', '十五',
    '十六', '十七', '十八', '十九', '二十', '二十一', '二十二', '二十三', '二十四', '二十五', '二十六',
    '二十七', '二十八', '二十九', '三十', '三十一'].forEach((cn, i) => { dayMap[`${cn}号`] = String(i + 1).padStart(2, '0'); });
  const year = new Date().getFullYear();
  for (const [monthCN, monthNum] of Object.entries(monthMap)) {
    if (chineseDate.includes(monthCN)) {
      for (const [dayCN, dayNum] of Object.entries(dayMap)) {
        if (chineseDate.includes(dayCN)) return `${year}-${monthNum}-${dayNum}`;
      }
    }
  }
  return null;
};

const refreshDisplayDates = () => {
  chatHistory.value = chatHistory.value.map((chat) => ({ ...chat, displayDate: formatDate(chat.date) }));
};

const startDateCheckTimer = () => {
  const checkDateChange = () => {
    const { todayStr } = getTodayDate();
    if (lastCheckedDate && lastCheckedDate !== todayStr) refreshDisplayDates();
    lastCheckedDate = todayStr;
  };
  checkDateChange();
  dateCheckTimer = setInterval(checkDateChange, 60000);
};

const stopDateCheckTimer = () => {
  if (dateCheckTimer) {
    clearInterval(dateCheckTimer);
    dateCheckTimer = null;
  }
};

const createNewChat = (force = false) => {
  if (!force && messages.value.length === 0 && chatHistory.value.length > 0) return currentChatId.value;
  const id = generateId();
  const { todayStr } = getTodayDate();
  const existingNowIndex = chatHistory.value.findIndex((c) => c.displayDate === '现在');
  if (existingNowIndex !== -1) chatHistory.value.splice(existingNowIndex, 1);
  chatHistory.value.unshift({ id, date: todayStr, displayDate: '现在', isTemp: true, messages: [] });
  currentChatId.value = id;
  messages.value = [];
  return id;
};

const newChat = () => {
  if (isCreatingChat.value) return;
  isCreatingChat.value = true;
  try {
    if (messages.value.length > 0) {
      saveCurrentChat();
      createNewChat(true);
    } else if (chatHistory.value.length === 0) {
      createNewChat(true);
    }
  } finally {
    isCreatingChat.value = false;
  }
  inputText.value = '';
  selectedGrade.value = '';
  view.value = 'chat';
  activeReviewId.value = null;
};

const saveCurrentChat = () => {
  if (!currentChatId.value || messages.value.length === 0) return;
  const chatIndex = chatHistory.value.findIndex((c) => c.id === currentChatId.value);
  if (chatIndex !== -1) {
    chatHistory.value[chatIndex].messages = [...messages.value];
    chatHistory.value[chatIndex].displayDate = formatDate(chatHistory.value[chatIndex].date);
    chatHistory.value[chatIndex].reviewId = findReviewId(chatHistory.value[chatIndex]);
    saveHistory();
    if (currentUser.value) syncHistory();
  }
};

const loadChat = (chatId) => {
  if (currentChatId.value === chatId) { view.value = 'chat'; return; }
  saveCurrentChat();
  const chat = chatHistory.value.find((c) => c.id === chatId);
  if (chat) {
    currentChatId.value = chatId;
    messages.value = hydrateAttachments([...chat.messages]);
    view.value = 'chat';
    activeReviewId.value = null;
  }
};

const saveHistory = () => {
  try {
    let dataToSave = chatHistory.value.map((chat) => ({ id: chat.id, date: chat.date, messages: chat.messages }));
    dataToSave = dataToSave.filter((chat) => isDateWithinWeek(chat.date) && chat.messages.length > 0);
    if (dataToSave.length > MAX_HISTORY) dataToSave = dataToSave.slice(0, MAX_HISTORY);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
  } catch (e) {
    console.error('保存历史记录失败:', e);
  }
};

// ---------------- 生命周期 ----------------
onMounted(() => {
  currentUser.value = localStorage.getItem('ai_teacher_user') || '';
  const token = getToken();
  if (token) {
    verifyTokenAndLoad(token);
  } else {
    loadLocalHistoryData();
    startDateCheckTimer();
    if (chatHistory.value.length === 0) {
      createNewChat(true);
    } else {
      const lastChat = chatHistory.value[0];
      currentChatId.value = lastChat.id;
      messages.value = hydrateAttachments([...lastChat.messages]);
    }
  }
});

onUnmounted(() => {
  stopDateCheckTimer();
  pollTimers.forEach((timer) => clearInterval(timer));
  pollTimers.clear();
});

const verifyTokenAndLoad = async (token) => {
  try {
    const response = await axios.get('/get_history', { headers: { Authorization: `Bearer ${token}` } });
    if (response.data.success) {
      const decoded = parseJwt(token);
      currentUser.value = decoded.username || localStorage.getItem('ai_teacher_user') || '';
      await loadHistoryFromServer();
      startDateCheckTimer();
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem('ai_teacher_user');
    }
  } catch (error) {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem('ai_teacher_user');
    loadLocalHistoryData();
    startDateCheckTimer();
    if (chatHistory.value.length === 0) {
      createNewChat(true);
    } else {
      const lastChat = chatHistory.value[0];
      currentChatId.value = lastChat.id;
      messages.value = hydrateAttachments([...lastChat.messages]);
    }
  }
};

const parseJwt = (token) => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch (e) {
    return {};
  }
};

const previewImageFull = (imageUrl) => { fullscreenImage.value = imageUrl; };
const closeFullscreenImage = () => { fullscreenImage.value = null; };
</script>

<style scoped>
/* 批改页需要占满剩余空间，且自身管理滚动 */
.main-content > :deep(.review-workbench) { flex: 1; min-height: 0; }

/* 批改结果页不显示侧边栏时，主内容区占满并去掉左侧留白 */
.main-page.reviewing { overflow: hidden; }
.main-page.reviewing .main-content { padding-left: 0; padding-top: 0; }

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.history-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
