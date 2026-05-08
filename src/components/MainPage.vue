<template>
  <div class="main-page" :class="{'sidebar-collapsed': !isSidebarOpen}">
    <!-- 左侧边栏 -->
    <div class="sidebar" :class="{'sidebar-hidden': !isSidebarOpen}">
      <!-- 顶部标题 -->
      <div class="sidebar-header">
        <h1 class="system-title">AI智能批改教师</h1>
        <button class="sidebar-toggle-btn" @click="toggleSidebar">
          {{ isSidebarOpen ? '◀' : '▶' }}
        </button>
      </div>

      <!-- 按钮区域 -->
      <div class="sidebar-buttons">
        <button class="sidebar-action-btn" @click="newChat">
          <span class="btn-icon">+</span>
          <span class="btn-text">新对话</span>
        </button>
        <button class="sidebar-action-btn" @click="syncHistory" :disabled="isSyncing">
          <span class="btn-icon">{{ isSyncing ? '⏳' : '🔄' }}</span>
          <span class="btn-text">{{ isSyncing ? '同步中...' : '同步' }}</span>
        </button>
      </div>

      <!-- 对话历史列表 -->
      <div class="history-section">
        <template v-for="(group, date) in groupedHistory" :key="date">
          <div class="history-group">
            <div class="history-time">{{ date }}</div>
            <div
              v-for="chat in group"
              :key="chat.id"
              class="history-item"
              :class="{'active': currentChatId === chat.id}"
              @click="loadChat(chat.id)"
            >
              {{ (chat.messages[0]?.content || '').substring(0, 20) }}{{ (chat.messages[0]?.content || '').length > 20 ? '...' : '' }}
            </div>
          </div>
        </template>
      </div>

      <!-- 用户信息 -->
      <div class="user-info-sidebar">
        <div class="avatar">{{ currentUser?.charAt(0).toUpperCase() || 'U' }}</div>
        <div class="user-details">
          <div class="user-name">{{ currentUser || '用户' }}</div>
          <button class="logout-btn" @click="handleLogout">退出登录</button>
        </div>
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="main-content">
      <!-- 侧边栏隐藏时显示的工具栏 -->
      <div v-if="!isSidebarOpen" class="collapsed-toolbar">
        <button class="collapsed-btn" @click="toggleSidebar" title="展开侧边栏">
          ▶
        </button>
        <button class="collapsed-action-btn" @click="newChat" title="新对话">
          <span>+</span>
        </button>
        <button class="collapsed-action-btn" @click="syncHistory" :disabled="isSyncing" title="同步">
          <span>{{ isSyncing ? '⏳' : '🔄' }}</span>
        </button>
      </div>

      <!-- 对话历史 -->
      <ChatHistory 
        :messages="messages" 
        @preview-image="previewImageFull"
      />

      <!-- 输入区域 -->
      <InputArea
        v-model="inputText"
        :essay-type="selectedEssayType"
        :is-loading="isLoading"
        @update:essay-type="selectEssayType"
        @send="handleSend"
        @file-upload="handleFileUpload"
      />
    </div>

    <!-- 错误提示弹窗 -->
    <div v-if="errorMessage" class="error-toast">
      <div class="error-content">
        <span class="error-icon">⚠️</span>
        <span class="error-text">{{ errorMessage }}</span>
        <button class="error-close" @click="errorMessage = ''">×</button>
      </div>
    </div>

    <!-- 全屏图片预览模态框 -->
    <div v-if="fullscreenImage" class="fullscreen-overlay" @click="closeFullscreenImage">
      <div class="fullscreen-content" @click.stop>
        <img :src="fullscreenImage" alt="全屏预览" class="fullscreen-img" />
        <button class="fullscreen-close" @click="closeFullscreenImage">×</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue';
import axios from 'axios';
import ChatHistory from './ChatHistory.vue';
import InputArea from './InputArea.vue';

// 定义emit事件
const emit = defineEmits(['logout']);

// 认证相关状态
const currentUser = ref('');
const isSyncing = ref(false);
const fullscreenImage = ref(null);

// 消息和聊天相关状态
const messages = ref([]);
const inputText = ref('');
const isLoading = ref(false);
const isSidebarOpen = ref(true);
const errorMessage = ref('');
const chatHistory = ref([]);
const currentChatId = ref(null);
const isCreatingChat = ref(false);

// 作文体裁选择状态
const selectedEssayType = ref('');

let dateCheckTimer = null;
let lastCheckedDate = '';

// 常量定义
const STORAGE_KEY = 'ai_teacher_chat_history';
const TOKEN_KEY = 'ai_teacher_token';
const MAX_HISTORY = 100;
const MAX_HISTORY_DAYS = 7;

const essayKeywords = ['作文', '文章', '写作', ' essay', '作文题', '请批改', '请点评', '写一篇', '写了一篇', '字数', '段落', '开头', '结尾', '议论文', '记叙文', '说明文'];
const consultationKeywords = ['如何', '怎么', '怎样', '为什么', '请问', '我想问', '问一下', '咨询', '方法', '技巧', '策略', '要点', '建议', '告诉我', '分析一下'];

// 按日期分组的历史记录
const groupedHistory = computed(() => {
  const groups = {};
  chatHistory.value.forEach(chat => {
    const displayDate = chat.displayDate || formatDate(chat.date);
    if (!groups[displayDate]) {
      groups[displayDate] = [];
    }
    groups[displayDate].push(chat);
  });
  
  const dateOrder = ['现在', '今天', '昨天'];
  const sortedDates = Object.keys(groups).sort((a, b) => {
    const indexA = dateOrder.indexOf(a);
    const indexB = dateOrder.indexOf(b);
    if (indexA !== -1 && indexB !== -1) {
      return indexA - indexB;
    }
    if (indexA !== -1) return -1;
    if (indexB !== -1) return 1;
    return b.localeCompare(a);
  });
  
  const sortedGroups = {};
  sortedDates.forEach(date => {
    sortedGroups[date] = groups[date];
  });
  return sortedGroups;
});

// 判断是否为作文提交
// 判断逻辑：优先根据文本长度判断，关键词作为辅助
const isEssaySubmission = (text) => {
  if (!text || typeof text !== 'string') return false;
  
  const trimmedText = text.trim();
  const textLength = trimmedText.length;
  
  // 1. 最小长度检查：至少100字才可能是作文
  if (textLength < 100) {
    console.log('[作文检测] 文本过短(' + textLength + '字)，不是作文提交');
    return false;
  }
  
  const hasEssayKeywords = essayKeywords.some(kw => trimmedText.includes(kw));
  const hasConsultKeywords = consultationKeywords.some(kw => trimmedText.includes(kw));
  const isLongText = textLength > 200;
  
  // 2. 长文本优先判定：超过500字且包含作文关键词，直接判定为作文
  //    即使包含咨询关键词也优先考虑是作文（用户可能在作文中提问）
  if (textLength > 500 && hasEssayKeywords) {
    console.log('[作文检测] 长文本(' + textLength + '字)且包含作文关键词，判定为作文提交');
    return true;
  }
  
  // 3. 超长文本（超过800字）直接判定为作文，无需关键词
  if (textLength > 800) {
    console.log('[作文检测] 超长文本(' + textLength + '字)，直接判定为作文提交');
    return true;
  }
  
  // 4. 咨询类问题排除（仅适用于短文本）
  if (hasConsultKeywords && !hasEssayKeywords && textLength < 300) {
    console.log('[作文检测] 短文本且包含咨询关键词，不是作文提交');
    return false;
  }
  
  // 5. 包含作文关键词且文本较长，判定为作文提交
  if (hasEssayKeywords && isLongText) {
    console.log('[作文检测] 包含作文关键词且文本较长(' + textLength + '字)，判定为作文提交');
    return true;
  }
  
  // 6. 纯长文本（超过500字）也判定为作文提交
  if (textLength > 500) {
    console.log('[作文检测] 文本超过500字(' + textLength + '字)，判定为作文提交');
    return true;
  }
  
  // 7. 中等长度文本（200-500字）需要包含作文关键词才判定为作文
  if (isLongText && hasEssayKeywords) {
    console.log('[作文检测] 中等长度文本(' + textLength + '字)且包含作文关键词，判定为作文提交');
    return true;
  }
  
  console.log('[作文检测] 未满足作文提交条件，文本长度:' + textLength + '字');
  return false;
};

// 获取认证令牌
const getToken = () => {
  return localStorage.getItem(TOKEN_KEY);
};

// 用户登出
const handleLogout = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem('ai_teacher_user');
  emit('logout');
};

// 从服务器加载历史记录
const loadHistoryFromServer = async () => {
  const token = getToken();
  if (!token) return;
  
  try {
    const response = await axios.get('/get_history', {
      headers: { Authorization: `Bearer ${token}` }
    });
    
    if (response.data.success) {
      const serverHistory = response.data.history;
      const localHistory = loadLocalHistory();
      const mergedHistory = mergeHistory(serverHistory, localHistory);
      
      chatHistory.value = mergedHistory
        .filter(chat => chat.messages && chat.messages.length > 0 && isDateWithinWeek(chat.date))
        .map(chat => ({
          ...chat,
          displayDate: formatDate(chat.date)
        }));
      
      saveLocalHistory(chatHistory.value);
      
      if (chatHistory.value.length > 0) {
        const lastChat = chatHistory.value[0];
        currentChatId.value = lastChat.id;
        messages.value = [...lastChat.messages];
      } else {
        createNewChat(true);
      }
    }
  } catch (error) {
    console.error('从服务器加载历史记录失败:', error);
    loadLocalHistoryData();
  }
};

// 同步历史记录到服务器
const syncHistory = async () => {
  const token = getToken();
  if (!token) return;
  
  isSyncing.value = true;
  try {
    const historyToSync = chatHistory.value.map(chat => ({
      id: chat.id,
      date: chat.date,
      messages: chat.messages
    }));
    
    const response = await axios.post('/save_history', {
      history: historyToSync
    }, {
      headers: { Authorization: `Bearer ${token}` }
    });
    
    if (response.data.success) {
      showError('历史记录同步成功');
    } else {
      showError('同步失败');
    }
  } catch (error) {
    showError('同步失败，请检查网络连接');
  } finally {
    isSyncing.value = false;
  }
};

// 合并历史记录
const mergeHistory = (serverHistory, localHistory) => {
  const merged = {};
  localHistory.forEach(chat => {
    merged[chat.id] = chat;
  });
  serverHistory.forEach(chat => {
    merged[chat.id] = chat;
  });
  return Object.values(merged).sort((a, b) => new Date(b.date) - new Date(a.date));
};

// 加载本地历史记录
const loadLocalHistory = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch (e) {
    return [];
  }
};

// 保存本地历史记录
const saveLocalHistory = (history) => {
  try {
    const dataToSave = history.map(chat => ({
      id: chat.id,
      date: chat.date,
      messages: chat.messages
    })).filter(chat => isDateWithinWeek(chat.date)).slice(0, MAX_HISTORY);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
  } catch (e) {
    console.error('保存本地历史记录失败:', e);
  }
};

// 从本地加载历史记录数据
const loadLocalHistoryData = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const history = JSON.parse(saved);
      chatHistory.value = history
        .filter(chat => chat.messages && chat.messages.length > 0 && isDateWithinWeek(chat.date))
        .map(chat => ({
          ...chat,
          displayDate: formatDate(chat.date)
        }));
    }
  } catch (e) {
    chatHistory.value = [];
  }
};

// 生成唯一ID
const generateId = () => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
};

// 检查日期是否在最近一周内
const isDateWithinWeek = (dateStr) => {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - MAX_HISTORY_DAYS);
  return date >= weekAgo;
};

// 获取今天的日期信息
const getTodayDate = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const day = now.getDate();
  const today = new Date(year, month, day);
  const yesterday = new Date(year, month, day - 1);
  
  const todayStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  const yesterdayStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, '0')}-${String(yesterday.getDate()).padStart(2, '0')}`;
  
  return { todayStr, yesterdayStr };
};

// 格式化日期显示
const formatDate = (dateStr) => {
  const { todayStr, yesterdayStr } = getTodayDate();
  const normalizedDate = normalizeDate(dateStr);
  
  if (!normalizedDate) return dateStr;
  if (normalizedDate === todayStr) return '今天';
  if (normalizedDate === yesterdayStr) return '昨天';
  
  const [year, month, day] = normalizedDate.split('-');
  return `${year}/${month}/${day}`;
};

// 解析中文日期
const parseChineseDate = (chineseDate) => {
  const monthMap = {
    '一月': '01', '二月': '02', '三月': '03', '四月': '04',
    '五月': '05', '六月': '06', '七月': '07', '八月': '08',
    '九月': '09', '十月': '10', '十一月': '11', '十二月': '12'
  };
  
  const dayMap = {
    '一号': '01', '二号': '02', '三号': '03', '四号': '04', '五号': '05',
    '六号': '06', '七号': '07', '八号': '08', '九号': '09', '十号': '10',
    '十一号': '11', '十二号': '12', '十三号': '13', '十四号': '14', '十五号': '15',
    '十六号': '16', '十七号': '17', '十八号': '18', '十九号': '19', '二十号': '20',
    '二十一号': '21', '二十二号': '22', '二十三号': '23', '二十四号': '24', '二十五号': '25',
    '二十六号': '26', '二十七号': '27', '二十八号': '28', '二十九号': '29', '三十号': '30',
    '三十一号': '31'
  };
  
  const now = new Date();
  const year = now.getFullYear();
  
  for (const [monthCN, monthNum] of Object.entries(monthMap)) {
    if (chineseDate.includes(monthCN)) {
      for (const [dayCN, dayNum] of Object.entries(dayMap)) {
        if (chineseDate.includes(dayCN)) {
          return `${year}-${monthNum}-${dayNum}`;
        }
      }
    }
  }
  return null;
};

// 规范化日期格式
const normalizeDate = (dateStr) => {
  if (!dateStr) return null;
  dateStr = dateStr.trim();
  
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return dateStr;
  }
  
  const parsed = parseChineseDate(dateStr);
  if (parsed) return parsed;
  
  return null;
};

// 刷新显示日期
const refreshDisplayDates = () => {
  chatHistory.value = chatHistory.value.map(chat => ({
    ...chat,
    displayDate: formatDate(chat.date)
  }));
};

// 启动日期检查定时器
const startDateCheckTimer = () => {
  const checkDateChange = () => {
    const { todayStr } = getTodayDate();
    if (lastCheckedDate && lastCheckedDate !== todayStr) {
      refreshDisplayDates();
    }
    lastCheckedDate = todayStr;
  };
  checkDateChange();
  dateCheckTimer = setInterval(checkDateChange, 60000);
};

// 停止日期检查定时器
const stopDateCheckTimer = () => {
  if (dateCheckTimer) {
    clearInterval(dateCheckTimer);
    dateCheckTimer = null;
  }
};

// 创建新对话
const createNewChat = (force = false) => {
  if (!force && messages.value.length === 0 && chatHistory.value.length > 0) {
    return currentChatId.value;
  }
  
  const id = generateId();
  const { todayStr } = getTodayDate();
  
  const existingNowIndex = chatHistory.value.findIndex(c => c.displayDate === '现在');
  if (existingNowIndex !== -1) {
    chatHistory.value.splice(existingNowIndex, 1);
  }
  
  const tempChat = {
    id,
    date: todayStr,
    displayDate: '现在',
    isTemp: true,
    messages: []
  };
  
  chatHistory.value.unshift(tempChat);
  currentChatId.value = id;
  messages.value = [];
  return id;
};

// 新建对话按钮点击处理
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
  selectedEssayType.value = '';
};

// 保存当前对话
const saveCurrentChat = () => {
  if (!currentChatId.value || messages.value.length === 0) return;
  
  const chatIndex = chatHistory.value.findIndex(c => c.id === currentChatId.value);
  if (chatIndex !== -1) {
    chatHistory.value[chatIndex].messages = [...messages.value];
    chatHistory.value[chatIndex].displayDate = formatDate(chatHistory.value[chatIndex].date);
    saveHistory();
    
    if (currentUser.value) {
      syncHistory();
    }
  }
};

// 加载指定对话
const loadChat = (chatId) => {
  if (currentChatId.value === chatId) return;
  
  saveCurrentChat();
  
  const chat = chatHistory.value.find(c => c.id === chatId);
  if (chat) {
    currentChatId.value = chatId;
    messages.value = [...chat.messages];
  }
};

// 切换侧边栏显示/隐藏状态
const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value;
};

// 加载历史记录
const loadHistory = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const history = JSON.parse(saved);
      chatHistory.value = history
        .filter(chat => chat.messages && chat.messages.length > 0 && isDateWithinWeek(chat.date))
        .map(chat => ({
          ...chat,
          displayDate: formatDate(chat.date)
        }));
    }
  } catch (e) {
    console.error('加载历史记录失败:', e);
    chatHistory.value = [];
  }
};

// 保存历史记录
const saveHistory = () => {
  try {
    let dataToSave = chatHistory.value.map(chat => ({
      id: chat.id,
      date: chat.date,
      messages: chat.messages
    }));
    
    dataToSave = dataToSave.filter(chat => isDateWithinWeek(chat.date) && chat.messages.length > 0);
    
    if (dataToSave.length > MAX_HISTORY) {
      dataToSave = dataToSave.slice(0, MAX_HISTORY);
    }
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
  } catch (e) {
    console.error('保存历史记录失败:', e);
  }
};

// 页面加载时执行
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
      if (lastChat && lastChat.messages.length > 0) {
        currentChatId.value = lastChat.id;
        messages.value = [...lastChat.messages];
      } else {
        currentChatId.value = lastChat.id;
        messages.value = [];
      }
    }
  }
});

// 验证token并加载历史记录
const verifyTokenAndLoad = async (token) => {
  try {
    const response = await axios.get('/get_history', {
      headers: { Authorization: `Bearer ${token}` }
    });
    
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
      messages.value = [...lastChat.messages];
    }
  }
};

// 解析JWT令牌
const parseJwt = (token) => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch (e) {
    return {};
  }
};

onUnmounted(() => {
  stopDateCheckTimer();
});

// 全屏预览图片
const previewImageFull = (imageUrl) => {
  fullscreenImage.value = imageUrl;
};

// 关闭全屏预览
const closeFullscreenImage = () => {
  fullscreenImage.value = null;
};

// 显示错误消息
const showError = (message) => {
  errorMessage.value = message;
  setTimeout(() => {
    errorMessage.value = '';
  }, 5000);
};

// 清理AI响应
const cleanAIResponse = (response, userMessage) => {
  let cleaned = response;
  
  if (userMessage && cleaned.startsWith(userMessage)) {
    cleaned = cleaned.substring(userMessage.length).trim();
  }
  
  const patterns = [
    new RegExp(`^用户说：${userMessage}\\s*`, 'i'),
    new RegExp(`^用户输入：${userMessage}\\s*`, 'i'),
    new RegExp(`^用户：${userMessage}\\s*`, 'i'),
    new RegExp(`^「${userMessage}」`, 'i'),
  ];
  
  patterns.forEach(pattern => {
    cleaned = cleaned.replace(pattern, '');
  });
  
  return cleaned.trim();
};

// 选择作文体裁
const selectEssayType = (type) => {
  selectedEssayType.value = type;
};

// 处理发送
const handleSend = async ({ content, essayType }) => {
  const userMessage = content.trim();
  const isEssay = isEssaySubmission(userMessage);
  
  if (isEssay && !essayType) {
    showError('请先选择作文体裁（议论文、记叙文或说明文）');
    return;
  }
  
  isLoading.value = true;
  
  messages.value.push({
    role: 'user',
    content: userMessage,
    type: isEssay ? 'essay_submission' : 'normal',
    essayType: isEssay ? essayType : null,
    timestamp: Date.now()
  });
  
  try {
    const requestData = {
      message: userMessage,
      type: isEssay ? 'essay_review' : 'consultation'
    };
    
    if (isEssay && essayType) {
      requestData.essay_type = essayType;
    }
    
    const response = await axios.post('/chat', requestData);
    
    if (response.data.success) {
      const data = response.data.data;
      const isEssayReview = data.score !== null || data.dimensions?.length > 0;
      
      if (isEssayReview) {
        const cleanedResponse = cleanAIResponse(data.raw_response || '', userMessage);
        messages.value.push({
          role: 'assistant',
          content: cleanedResponse,
          type: 'essay_review',
          timestamp: Date.now(),
          data: {
            score: data.score,
            totalScore: data.total_score || 50,
            essayType: data.essay_type || detectEssayType(userMessage),
            dimensions: data.dimensions || [],
            overallComment: data.overall_comment || '',
            improvements: data.improvements || [],
            summary: data.summary || null,
            rawResponse: data.raw_response || ''
          }
        });
      } else {
        const cleanedResponse = cleanAIResponse(data.raw_response || '', userMessage);
        messages.value.push({
          role: 'assistant',
          content: cleanedResponse,
          type: 'normal',
          timestamp: Date.now(),
          data: null
        });
      }
      
      saveCurrentChat();
    } else {
      showError(response.data.message || '处理请求失败');
      messages.value.push({
        role: 'assistant',
        content: '抱歉，处理请求时出现错误，请稍后重试。',
        type: 'normal',
        timestamp: Date.now()
      });
    }
  } catch (error) {
    console.error('API调用失败:', error);
    const errorMsg = error.response?.data?.message || '网络连接失败，请检查后端服务是否启动';
    showError(errorMsg);
    
    messages.value.push({
      role: 'assistant',
      content: '抱歉，处理请求时出现错误，请稍后重试。',
      type: 'normal',
      timestamp: Date.now()
    });
  } finally {
    isLoading.value = false;
  }
};

// 处理文件上传
const handleFileUpload = ({ file, type, data }) => {
  if (type === 'image') {
    messages.value.push({
      role: 'user',
      content: '',
      type: 'image',
      image: data,
      timestamp: Date.now()
    });
  } else if (type === 'text') {
    // 文件内容已通过InputArea处理
  }
};

// 检测作文类型
const detectEssayType = (text) => {
  if (text.includes('议论文')) return '议论文';
  if (text.includes('记叙文')) return '记叙文';
  if (text.includes('说明文')) return '说明文';
  
  if (text.includes('论点') || text.includes('论证') || text.includes('论据')) {
    return '议论文';
  }
  if (text.includes('记叙') || text.includes('叙事') || text.includes('描写')) {
    return '记叙文';
  }
  if (text.includes('说明') || text.includes('解释') || text.includes('介绍')) {
    return '说明文';
  }
  
  return '初中作文';
};
</script>