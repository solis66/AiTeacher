<template>
  <div class="app">
    <!-- 登录页面 -->
    <div v-if="!isLoggedIn && showLogin" class="login-container">
      <div class="login-form">
        <h2 class="login-title">AI智能批改教师</h2>
        <div class="form-group">
          <label>用户名</label>
          <input type="text" v-model="loginForm.username" placeholder="请输入用户名" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input type="password" v-model="loginForm.password" placeholder="请输入密码" @keydown.enter="login" />
        </div>
        <button class="login-btn" @click="login" :disabled="isLoading">
          {{ isLoading ? '登录中...' : '登录' }}
        </button>
        <p v-if="loginError" class="error-message">{{ loginError }}</p>
        <p class="hint-text">用户名: admin | 密码: 123456</p>
        <button class="back-btn" @click="showLogin = false">返回</button>
      </div>
    </div>

    <div v-if="!isLoggedIn && !showLogin" class="welcome-container">
      <div class="welcome-header">
        <h1 class="welcome-brand">AI智能批改教师</h1>
        <button class="header-login-btn" @click="showLogin = true">
          <span class="login-icon">👤</span>
          登录
        </button>
      </div>
      <div class="welcome-content">
        <div class="welcome-main">
          <div class="welcome-icon-large">🎓</div>
          <h2 class="welcome-heading">专业的AI作文批改助手</h2>
          <p class="welcome-desc">基于先进人工智能技术，为初中生提供精准、高效的作文批改服务</p>
          <div class="welcome-features">
            <div class="feature-item">
              <span class="feature-icon">✍️</span>
              <span class="feature-text">多维度评分</span>
            </div>
            <div class="feature-item">
              <span class="feature-icon">📝</span>
              <span class="feature-text">详细点评</span>
            </div>
            <div class="feature-item">
              <span class="feature-icon">💡</span>
              <span class="feature-text">改进建议</span>
            </div>
          </div>
          <button class="start-btn" @click="showLogin = true">
            开始使用
          </button>
        </div>
      </div>
    </div>

    <div v-else class="main-container" :class="{'sidebar-collapsed': !isSidebarOpen}">
      <!-- 左侧边栏 -->
      <div class="sidebar" :class="{'sidebar-hidden': !isSidebarOpen}">

        <!-- 顶部标题 -->
        <div class="sidebar-header" >
          <h1 class="system-title">AI智能批改教师</h1>
          <!-- 添加侧边栏按钮-->
          <button class="sidebar-toggle-btn" @click="toggleSidebar">
            {{ isSidebarOpen ? '◀' : '▶' }}
          </button>
        </div>

        <!-- 按钮区域 -->
        <div class="sidebar-buttons">
          <!-- 开启新对话按钮 -->
          <button class="sidebar-action-btn" @click="newChat">
            <span class="btn-icon">+</span>
            <span class="btn-text">新对话</span>
          </button>

          <!-- 同步按钮 -->
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
            <button class="logout-btn" @click="logout">退出登录</button>
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

        <!-- 欢迎信息 -->
        <div class="welcome-message" v-if="messages.length === 0">
          <div class="welcome-icon">🤖</div>
          <h2 class="welcome-title">欢迎来到AI智能批改老师</h2>
        </div>

        <!-- 对话历史 -->
        <div class="chat-history" ref="chatChontainer">
          <div class="message" v-for="(msg, index) in messages" :key="index" :class="msg.role">
            <!-- 普通对话消息 -->
            <div v-if="msg.type !== 'essay_review'" class="message-content">
              {{ msg.content }}
              <!-- 图片预览 -->
              <div v-if="msg.imageUrl" class="message-image">
                <img :src="msg.imageUrl" :alt="'图片'" class="preview-img" @click="previewImageFull(msg.imageUrl)" />
              </div>
            </div>

            <!-- 作文批改结果 -->
            <div v-else class="essay-review">
              <div class="review-header">
                <span class="review-title">📝 作文批改结果</span>
                <span class="essay-type-badge">{{ msg.data.essayType }}</span>
              </div>

              <!-- 总分显示 -->
              <div v-if="msg.data.score" class="score-section">
                <div class="score-circle">
                  <span class="score-value">{{ msg.data.score }}</span>
                  <span class="score-total">/{{ msg.data.totalScore }}</span>
                </div>
                <div class="score-label">总分</div>
              </div>

              <!-- 各维度评分 -->
              <div v-if="msg.data.dimensions && msg.data.dimensions.length > 0" class="dimensions-section">
                <h4 class="section-title">各项评分</h4>
                <div class="dimension-item" v-for="(dim, idx) in msg.data.dimensions" :key="idx">
                  <span class="dimension-name">{{ dim.name }}</span>
                  <div class="dimension-bar">
                    <div class="dimension-fill" :style="{width: getDimensionPercent(dim) + '%'}"></div>
                  </div>
                  <span class="dimension-score">{{ dim.score }}分</span>
                </div>
              </div>

              <!-- 总体评价 -->
              <div v-if="msg.data.overallComment" class="comment-section">
                <h4 class="section-title">总体评价</h4>
                <p class="overall-comment">{{ msg.data.overallComment }}</p>
              </div>

              <!-- 改进建议 -->
              <div v-if="msg.data.improvements && msg.data.improvements.length > 0" class="improvements-section">
                <h4 class="section-title">改进建议</h4>
                <ul class="improvements-list">
                  <li v-for="(item, idx) in msg.data.improvements" :key="idx">{{ item }}</li>
                </ul>
              </div>

              <!-- 原始回复 -->
              <div class="raw-response">
                <div class="raw-header" @click="toggleRawResponse(index)">
                  <span>完整回复</span>
                  <span class="toggle-icon">{{ expandedSections[index] ? '▲' : '▼' }}</span>
                </div>
                <div v-if="expandedSections[index]" class="raw-content">
                  {{ msg.data.rawResponse }}
                </div>
              </div>
            </div>
          </div>

          <!-- 加载状态 -->
          <div v-if="isLoading" class="loading">
            <span class="loading-dot">.</span>
            <span class="loading-dot">.</span>
            <span class="loading-dot">.</span>
          </div>
        </div>

        <!-- 输入区域 -->
        <div class="input-area">
          <textarea
            class="input-textarea"
            :placeholder="inputPlaceholder"
            v-model="inputText"
            @input="updateCharCount"
            @keydown="handleKeydown"
            @paste="handlePaste"
            maxlength="5000"
          ></textarea>
          <div class="input-footer">
            <div class="input-left">
              <span class="char-count">{{ charCount }}/5000</span>
              <!-- 文件上传按钮 -->
              <label class="upload-btn" :disabled="isLoading">
                <input type="file" accept=".txt" @change="handleFileUpload" class="file-input" />
                <span class="upload-icon">📁</span>
                上传文件
              </label>
              <!-- 图片识别按钮 -->
              <label class="upload-btn image-upload-btn" :disabled="isLoading">
                <input type="file" accept=".jpg,.png" @change="handleImageUpload" class="file-input" />
                <span class="upload-icon">🖼️</span>
                图片识别
              </label>
            </div>
            <div class="input-right">
              <span class="shortcut-hint">Enter 发送 | Shift+Enter 换行</span>
              <button class="send-btn" @click="sendMessage" :disabled="isLoading || !canSendMessage()">
                <span class="send-icon">↑</span>
              </button>
            </div>
          </div>
          <!-- 图片预览 -->
          <div v-if="previewImage" class="image-preview">
            <img :src="previewImage" alt="预览图片" />
            <button class="remove-image-btn" @click="clearPreviewImage">×</button>
          </div>
        </div>
      </div>
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
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue';
import axios from 'axios';

// 认证相关状态
const isLoggedIn = ref(false);
const currentUser = ref('');
const loginForm = ref({ username: '', password: '' });
const loginError = ref('');
const isSyncing = ref(false);
const showLogin = ref(false);
const previewImage = ref(null);
const hasImageRecognition = ref(false);
const lastRecognizedText = ref('');
const fullscreenImage = ref(null);

// 消息和聊天相关状态
const messages = ref([]);
const inputText = ref('');
const charCount = ref(0);
const isLoading = ref(false);
const isSidebarOpen = ref(true);
const chatChontainer = ref(null);
const errorMessage = ref('');
const expandedSections = ref({});
const chatHistory = ref([]);
const currentChatId = ref(null);
const isCreatingChat = ref(false);
let dateCheckTimer = null;
let lastCheckedDate = '';

/**
 * 按日期分组的历史记录
 * 将chatHistory按displayDate分组，确保每个日期分类只出现一次
 * @returns {Object} - 以日期为键，聊天记录数组为值的对象
 */
const groupedHistory = computed(() => {
  const groups = {};
  
  // 遍历所有聊天记录
  chatHistory.value.forEach(chat => {
    // 获取显示日期（优先使用displayDate，否则格式化date字段）
    const displayDate = chat.displayDate || formatDate(chat.date);
    
    // 如果该日期分组不存在，创建新数组
    if (!groups[displayDate]) {
      groups[displayDate] = [];
    }
    
    // 将聊天记录添加到对应日期分组
    groups[displayDate].push(chat);
  });
  
  // 定义日期排序顺序
  const dateOrder = ['现在', '今天', '昨天'];
  
  // 按日期顺序排序
  const sortedDates = Object.keys(groups).sort((a, b) => {
    const indexA = dateOrder.indexOf(a);
    const indexB = dateOrder.indexOf(b);
    
    // 如果两个都在dateOrder中，按顺序排列
    if (indexA !== -1 && indexB !== -1) {
      return indexA - indexB;
    }
    
    // '现在'、'今天'、'昨天'排在前面
    if (indexA !== -1) return -1;
    if (indexB !== -1) return 1;
    
    // 其他日期按时间倒序排列（新的在前）
    return b.localeCompare(a);
  });
  
  // 重新构建有序的分组对象
  const sortedGroups = {};
  sortedDates.forEach(date => {
    sortedGroups[date] = groups[date];
  });
  
  return sortedGroups;
});

const STORAGE_KEY = 'ai_teacher_chat_history';
const TOKEN_KEY = 'ai_teacher_token';
const MAX_HISTORY = 100;
const MAX_HISTORY_DAYS = 7;

const essayKeywords = ['作文', '文章', '写作', ' essay', '作文题', '请批改', '请点评', '写一篇', '写了一篇', '字数', '段落', '开头', '结尾', '议论文', '记叙文', '说明文'];
const consultationKeywords = ['如何', '怎么', '怎样', '为什么', '请问', '我想问', '问一下', '咨询', '方法', '技巧', '策略', '要点', '建议', '告诉我', '分析一下'];

/**
 * 判断是否为作文提交
 * @param {string} text - 用户输入的文本
 * @returns {boolean} - 是否为作文提交
 */
const isEssaySubmission = (text) => {
  const hasEssayKeywords = essayKeywords.some(kw => text.includes(kw));
  const hasConsultKeywords = consultationKeywords.some(kw => text.includes(kw));
  const isLongText = text.length > 200;

  // 如果文本很短（小于30字），即使包含作文关键词也不是作文提交
  if (text.length < 30) {
    return false;
  }

  // 如果包含咨询关键词（尤其是明确的请求词如"告诉我"），优先判定为咨询
  if (hasConsultKeywords) {
    return false;
  }

  // 如果包含作文关键词且文本较长，判定为作文提交
  if (hasEssayKeywords && isLongText) {
    return true;
  }

  // 纯长文本（超过500字）也判定为作文提交
  if (text.length > 500) {
    return true;
  }

  return isLongText;
};

/**
 * 获取认证令牌
 * @returns {string} - JWT令牌
 */
const getToken = () => {
  return localStorage.getItem(TOKEN_KEY);
};

/**
 * 设置认证令牌
 * @param {string} token - JWT令牌
 */
const setToken = (token) => {
  localStorage.setItem(TOKEN_KEY, token);
};

/**
 * 清除认证令牌
 */
const clearToken = () => {
  localStorage.removeItem(TOKEN_KEY);
};

/**
 * 用户登录
 */
const login = async () => {
  if (!loginForm.value.username || !loginForm.value.password) {
    loginError.value = '请输入用户名和密码';
    return;
  }

  isLoading.value = true;
  loginError.value = '';

  try {
    const response = await axios.post('/api/login', {
      username: loginForm.value.username,
      password: loginForm.value.password
    });

    if (response.data.success) {
      setToken(response.data.token);
      currentUser.value = response.data.username;
      isLoggedIn.value = true;
      await loadHistoryFromServer();
    } else {
      loginError.value = response.data.error || '登录失败';
    }
  } catch (error) {
    loginError.value = error.response?.data?.error || '登录失败，请检查网络连接';
  } finally {
    isLoading.value = false;
  }
};

/**
 * 用户登出
 */
const logout = () => {
  clearToken();
  isLoggedIn.value = false;
  currentUser.value = '';
  chatHistory.value = [];
  messages.value = [];
  currentChatId.value = null;
};

/**
 * 从服务器加载历史记录
 */
const loadHistoryFromServer = async () => {
  const token = getToken();
  if (!token) return;

  try {
    const response = await axios.get('/api/get_history', {
      headers: { Authorization: `Bearer ${token}` }
    });

    if (response.data.success) {
      const serverHistory = response.data.history;
      const localHistory = loadLocalHistory();

      // 合并历史记录（服务器优先级更高）
      const mergedHistory = mergeHistory(serverHistory, localHistory);
      chatHistory.value = mergedHistory
        .filter(chat => chat.messages && chat.messages.length > 0 && isDateWithinWeek(chat.date))
        .map(chat => ({
          ...chat,
          displayDate: formatDate(chat.date)
        }));

      // 保存到本地
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
    // 回退到本地存储
    loadLocalHistoryData();
  }
};

/**
 * 同步历史记录到服务器
 */
const syncHistory = async () => {
  if (!isLoggedIn.value) return;

  isSyncing.value = true;

  try {
    const token = getToken();
    if (!token) return;

    const historyToSync = chatHistory.value.map(chat => ({
      id: chat.id,
      date: chat.date,
      messages: chat.messages
    }));

    const response = await axios.post('/api/save_history', {
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

/**
 * 合并历史记录
 * @param {array} serverHistory - 服务器历史记录
 * @param {array} localHistory - 本地历史记录
 * @returns {array} - 合并后的历史记录
 */
const mergeHistory = (serverHistory, localHistory) => {
  const merged = {};

  // 先添加本地记录
  localHistory.forEach(chat => {
    merged[chat.id] = chat;
  });

  // 用服务器记录覆盖
  serverHistory.forEach(chat => {
    merged[chat.id] = chat;
  });

  return Object.values(merged).sort((a, b) => {
    return new Date(b.date) - new Date(a.date);
  });
};

/**
 * 加载本地历史记录
 */
const loadLocalHistory = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch (e) {
    return [];
  }
};

/**
 * 保存本地历史记录
 * @param {array} history - 历史记录数组
 */
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

/**
 * 从本地加载历史记录数据（用于未登录状态）
 */
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

const getDimensionPercent = (dim) => {
  const maxScores = {
    '立意与中心': 12,
    '论点与论证': 18,
    '结构与层次': 9,
    '语言表达': 12,
    '例证与材料运用': 6,
    '书写与规范': 3,
    '选材与内容': 18,
    '细节与表现': 6,
    '内容与材料': 18,
    '方法与技巧': 6
  };
  const max = maxScores[dim.name] || 12;
  return Math.min((dim.score / max) * 100, 100);
};

const inputPlaceholder = computed(() => {
  return '给AI智能批改教师发送消息，或输入作文内容进行批改...\n\n提示：输入作文获取批改建议，输入问题获取咨询回复';
});

const generateId = () => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
};

/**
 * 检查日期是否在最近一周内
 * @param {string} dateStr - 日期字符串，格式为 YYYY-MM-DD
 * @returns {boolean} - 如果日期在一周内返回true，否则返回false
 */
const isDateWithinWeek = (dateStr) => {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - MAX_HISTORY_DAYS);
  
  return date >= weekAgo;
};

/**
 * 获取今天的日期信息
 * @returns {object} - 包含todayStr, yesterdayStr, todayDateStr
 */
const getTodayDate = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const day = now.getDate();

  const today = new Date(year, month, day);
  const yesterday = new Date(year, month, day - 1);

  const todayStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  const yesterdayStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, '0')}-${String(yesterday.getDate()).padStart(2, '0')}`;
  const todayDateStr = now.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' });

  return { todayStr, yesterdayStr, todayDateStr };
};

/**
 * 格式化日期显示
 * @param {string} dateStr - 日期字符串，格式为 YYYY-MM-DD
 * @returns {string} - 格式化后的日期显示（今天、昨天或 YYYY/MM/DD 格式）
 */
const formatDate = (dateStr) => {
  const { todayStr, yesterdayStr } = getTodayDate();

  const normalizedDate = normalizeDate(dateStr);
  if (!normalizedDate) {
    return dateStr;
  }

  if (normalizedDate === todayStr) {
    return '今天';
  }
  if (normalizedDate === yesterdayStr) {
    return '昨天';
  }

  // 将 YYYY-MM-DD 格式转换为 YYYY/MM/DD 格式显示
  const [year, month, day] = normalizedDate.split('-');
  return `${year}/${month}/${day}`;
};

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

const normalizeDate = (dateStr) => {
  if (!dateStr) return null;

  dateStr = dateStr.trim();

  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return dateStr;
  }

  const parsed = parseChineseDate(dateStr);
  if (parsed) {
    console.log('[normalizeDate] 中文日期转换:', dateStr, '->', parsed);
    return parsed;
  }

  return null;
};

const refreshDisplayDates = () => {
  chatHistory.value = chatHistory.value.map(chat => ({
    ...chat,
    displayDate: formatDate(chat.date)
  }));
};

const startDateCheckTimer = () => {
  const checkDateChange = () => {
    const { todayStr } = getTodayDate();
    if (lastCheckedDate && lastCheckedDate !== todayStr) {
      console.log('[日期检查] 日期已变化，刷新显示日期');
      refreshDisplayDates();
    }
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

/**
 * 加载历史记录
 * 从localStorage读取历史记录，并过滤掉一周前的记录
 */
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

/**
 * 保存历史记录
 * 将历史记录保存到localStorage，同时清理超出限制的记录
 * "现在"分类保存时转换为实际日期
 */
const saveHistory = () => {
  try {
    let dataToSave = chatHistory.value.map(chat => ({
      id: chat.id,
      date: chat.date,
      messages: chat.messages
    }));

    // 过滤一周前的记录和空消息记录
    dataToSave = dataToSave.filter(chat => 
      isDateWithinWeek(chat.date) && chat.messages.length > 0
    );

    // 限制最大记录数
    if (dataToSave.length > MAX_HISTORY) {
      dataToSave = dataToSave.slice(0, MAX_HISTORY);
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
  } catch (e) {
    console.error('保存历史记录失败:', e);
  }
};

/**
 * 创建新对话
 * 创建"现在"临时分类，用户发送消息后暂存至此分类
 * @param {boolean} force - 是否强制创建新对话
 * @returns {string} - 新对话的ID
 */
const createNewChat = (force = false) => {
  // 如果当前没有消息且已有对话，不创建新对话
  if (!force && messages.value.length === 0 && chatHistory.value.length > 0) {
    return currentChatId.value;
  }

  const id = generateId();
  const { todayStr } = getTodayDate();

  // 查找并移除已存在的"现在"分类
  const existingNowIndex = chatHistory.value.findIndex(c => c.displayDate === '现在');
  if (existingNowIndex !== -1) {
    chatHistory.value.splice(existingNowIndex, 1);
  }

  // 创建"现在"临时对话（用户发送消息后暂存至此）
  const tempChat = {
    id,
    date: todayStr,
    displayDate: '现在',
    isTemp: true,
    messages: []
  };

  // 将"现在"分类放在列表顶部
  chatHistory.value.unshift(tempChat);

  currentChatId.value = id;
  messages.value = [];

  return id;
};

/**
 * 新建对话按钮点击处理
 * 只有当当前对话有消息时才保存并创建新对话
 */
const newChat = () => {
  if (isCreatingChat.value) {
    return;
  }

  isCreatingChat.value = true;

  try {
    if (messages.value.length > 0) {
      saveCurrentChat();
      createNewChat(true);
    } else if (chatHistory.value.length === 0) {
      createNewChat(true);
    }
    // 如果当前无消息且已有对话，不做任何操作
  } finally {
    isCreatingChat.value = false;
  }

  inputText.value = '';
  updateCharCount();
  expandedSections.value = {};
};

/**
 * 保存当前对话
 */
const saveCurrentChat = () => {
  if (!currentChatId.value || messages.value.length === 0) return;

  const chatIndex = chatHistory.value.findIndex(c => c.id === currentChatId.value);
  if (chatIndex !== -1) {
    chatHistory.value[chatIndex].messages = [...messages.value];
    chatHistory.value[chatIndex].displayDate = formatDate(chatHistory.value[chatIndex].date);
    saveHistory();

    // 如果已登录，异步同步到服务器
    if (isLoggedIn.value) {
      syncHistory();
    }
  }
};

/**
 * 加载指定对话
 * @param {string} chatId - 对话ID
 */
const loadChat = (chatId) => {
  if (currentChatId.value === chatId) return;

  saveCurrentChat();

  const chat = chatHistory.value.find(c => c.id === chatId);
  if (chat) {
    currentChatId.value = chatId;
    messages.value = [...chat.messages];

    nextTick(() => {
      scrollToBottom();
    });
  }
};

/**
 * 切换侧边栏显示/隐藏状态
 */
const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value;
};

/**
 * 页面加载时执行
 */
onMounted(() => {
  // 检查是否有保存的token
  const token = getToken();
  if (token) {
    // 尝试验证token并加载历史记录
    verifyTokenAndLoad(token);
  } else {
    // 未登录状态，加载本地历史记录（如果有）
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

  updateCharCount();
});

/**
 * 验证token并加载历史记录
 */
const verifyTokenAndLoad = async (token) => {
  try {
    // 尝试获取用户信息或历史记录来验证token
    const response = await axios.get('/api/get_history', {
      headers: { Authorization: `Bearer ${token}` }
    });

    if (response.data.success) {
      // token有效，设置登录状态
      const decoded = parseJwt(token);
      currentUser.value = decoded.username;
      isLoggedIn.value = true;

      await loadHistoryFromServer();
      startDateCheckTimer();
    } else {
      // token无效，清除并显示登录页面
      clearToken();
    }
  } catch (error) {
    // token无效或服务器不可用，清除token
    clearToken();
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

/**
 * 解析JWT令牌
 * @param {string} token - JWT令牌
 * @returns {object} - 解码后的payload
 */
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

const updateCharCount = () => {
  charCount.value = inputText.value.length;
};

/**
 * 处理键盘事件
 * Enter键发送消息，Shift+Enter换行
 * @param {KeyboardEvent} event - 键盘事件对象
 */
const handleKeydown = (event) => {
  // Enter键且没有按住Shift
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
  // Shift+Enter组合键，保持换行行为
  // 不需要特别处理，textarea默认支持
};

/**
 * 处理粘贴事件，支持图片粘贴
 * @param {ClipboardEvent} event - 粘贴事件对象
 */
const handlePaste = (event) => {
  const items = event.clipboardData?.items;
  if (!items) return;

  for (const item of items) {
    if (item.type.startsWith('image/')) {
      event.preventDefault();
      const file = item.getAsFile();
      if (file) {
        handleImageFile(file);
      }
      break;
    }
  }
};

/**
 * 处理图片上传按钮点击
 * @param {Event} event - 文件选择事件
 */
const handleImageUpload = (event) => {
  const file = event.target.files[0];
  if (file) {
    handleImageFile(file);
  }
  event.target.value = '';
};

/**
 * 处理图片文件
 * @param {File} file - 图片文件对象
 */
const handleImageFile = async (file) => {
  // 验证文件类型
  if (!file.type.startsWith('image/')) {
    showError('仅支持上传图片文件');
    return;
  }

  // 验证文件格式
  const ext = file.name.toLowerCase().split('.').pop();
  if (!['jpg', 'jpeg', 'png'].includes(ext)) {
    showError('仅支持jpg和png格式的图片');
    return;
  }

  // 验证文件大小（限制5MB）
  if (file.size > 5 * 1024 * 1024) {
    showError('图片大小不能超过5MB');
    return;
  }

  try {
    isLoading.value = true;
    showError('正在识别图片内容...');

    // 显示预览
    previewImage.value = URL.createObjectURL(file);

    // 模拟图片识别（实际应用中调用OCR服务）
    await simulateImageRecognition(file);

    isLoading.value = false;
  } catch (error) {
    isLoading.value = false;
    previewImage.value = null;
    showError(`图片识别失败: ${error.message}`);
  }
};

/**
 * 模拟图片识别（实际应用中应调用OCR API）
 * 注意：当前仅保留图片预览功能，不自动填入识别内容
 * @param {File} file - 图片文件对象
 */
const simulateImageRecognition = async (file) => {
  // 模拟识别过程
  await new Promise(resolve => setTimeout(resolve, 1000));

  // 标记已上传图片，保持输入框空白由用户自主输入
  hasImageRecognition.value = true;
  
  showError('图片已上传，请输入您的查询或批改请求');
};

/**
 * 清除预览图片
 */
const clearPreviewImage = () => {
  if (previewImage.value) {
    URL.revokeObjectURL(previewImage.value);
    previewImage.value = null;
  }
  hasImageRecognition.value = false;
  lastRecognizedText.value = '';
};

/**
 * 全屏预览图片
 * @param {string} imageUrl - 图片URL
 */
const previewImageFull = (imageUrl) => {
  fullscreenImage.value = imageUrl;
};

/**
 * 关闭全屏预览
 */
const closeFullscreenImage = () => {
  fullscreenImage.value = null;
};

/**
 * 检查是否可以发送消息
 * @returns {boolean} - 是否可以发送
 */
const canSendMessage = () => {
  const text = inputText.value.trim();
  if (!text) return false;
  
  // 有图片时，允许发送任何非空文本
  if (hasImageRecognition.value) {
    return text.length > 0;
  }
  
  return true;
};

/**
 * 处理文件上传
 * @param {Event} event - 文件选择事件
 */
const handleFileUpload = async (event) => {
  const file = event.target.files[0];
  if (!file) return;

  // 验证文件类型
  if (!file.name.toLowerCase().endsWith('.txt')) {
    showError('仅支持上传.txt格式的文本文件');
    event.target.value = '';
    return;
  }

  // 验证文件大小（限制1MB）
  if (file.size > 1 * 1024 * 1024) {
    showError('文件大小不能超过1MB');
    event.target.value = '';
    return;
  }

  try {
    isLoading.value = true;
    showError('正在解析文件内容...');

    // 读取文件内容
    const content = await readFileContent(file);
    
    // 根据内容类型进行处理
    inputText.value = content;
    updateCharCount();

    showError('文件解析成功，内容已填入输入框');
  } catch (error) {
    showError(`文件解析失败: ${error.message}`);
  } finally {
    isLoading.value = false;
    event.target.value = '';
  }
};

/**
 * 读取文件内容
 * @param {File} file - 文件对象
 * @returns {Promise<string>} - 文件内容
 */
const readFileContent = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      const content = e.target.result;
      // 处理可能的编码问题（如UTF-8 BOM）
      const cleanedContent = content.replace(/^\uFEFF/, '');
      resolve(cleanedContent);
    };
    
    reader.onerror = () => {
      reject(new Error('文件读取失败'));
    };
    
    reader.readAsText(file, 'UTF-8');
  });
};

const toggleRawResponse = (index) => {
  expandedSections.value[index] = !expandedSections.value[index];
};

const showError = (message) => {
  errorMessage.value = message;
  setTimeout(() => {
    errorMessage.value = '';
  }, 5000);
};

const scrollToBottom = () => {
  nextTick(() => {
    if (chatChontainer.value) {
      chatChontainer.value.scrollTop = chatChontainer.value.scrollHeight;
    }
  });
};

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

/**
 * 发送消息
 * 验证输入内容，发送到后端API，并处理AI响应
 */
const sendMessage = async () => {
  // 检查是否可以发送
  if (!canSendMessage()) {
    if (hasImageRecognition.value) {
      showError('图片识别后请输入补充说明或指令');
    }
    return;
  }

  isLoading.value = true;

  const userMessage = inputText.value.trim();
  const isEssay = isEssaySubmission(userMessage);

  messages.value.push({
    role: 'user',
    content: userMessage,
    type: isEssay ? 'essay_submission' : 'normal'
  });

  scrollToBottom();

  const messageToSend = inputText.value;
  inputText.value = '';
  updateCharCount();
  
  // 清除图片识别状态
  clearPreviewImage();

  try {
    const response = await axios.post('/api/chat', {
      message: messageToSend,
      type: isEssay ? 'essay_review' : 'consultation'
    });

    if (response.data.success) {
      const data = response.data.data;

      const isEssayReview = data.score !== null || data.dimensions?.length > 0;

      if (isEssayReview) {
        const cleanedResponse = cleanAIResponse(data.raw_response || '', userMessage);

        messages.value.push({
          role: 'assistant',
          content: cleanedResponse,
          type: 'essay_review',
          data: {
            score: data.score,
            totalScore: data.total_score || 60,
            essayType: data.essay_type || detectEssayType(userMessage),
            dimensions: data.dimensions || [],
            overallComment: data.overall_comment || '',
            improvements: data.improvements || [],
            rawResponse: data.raw_response || ''
          }
        });
      } else {
        const cleanedResponse = cleanAIResponse(data.raw_response || '', userMessage);

        messages.value.push({
          role: 'assistant',
          content: cleanedResponse,
          type: 'normal',
          data: null
        });
      }

      saveCurrentChat();
    } else {
      showError(response.data.message || '处理请求失败');
      messages.value.push({
        role: 'assistant',
        content: '抱歉，处理请求时出现错误，请稍后重试。',
        type: 'normal'
      });
    }
  } catch (error) {
    console.error('API调用失败:', error);
    const errorMsg = error.response?.data?.message || '网络连接失败，请检查后端服务是否启动';
    showError(errorMsg);
    messages.value.push({
      role: 'assistant',
      content: '抱歉，处理请求时出现错误，请稍后重试。',
      type: 'normal'
    });
  } finally {
    isLoading.value = false;
    scrollToBottom();
  }
};

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

const handleDocUpload = (event) => {
  const file = event.target.files[0];
  if (file) {
    console.log('上传文档:', file.name);
  }
};
</script>

<style scoped>
.loading {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
  background-color: #f0f0f0;
  border-radius: 8px;
  margin: 12px 0;
  width: fit-content;
}

.loading-dot {
  font-size: 24px;
  font-weight: bold;
  color: #1a73e8;
  animation: dot-bounce 1.4s infinite ease-in-out;
}

.loading-dot:nth-child(2) { animation-delay: 0.2s; }
.loading-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

/* 作文批改结果样式 */
.essay-review {
  padding: 16px;
  background-color: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.review-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.review-title {
  font-size: 18px;
  font-weight: 600;
  color: #1a73e8;
}

.essay-type-badge {
  padding: 4px 12px;
  background-color: #e3f2fd;
  color: #1a73e8;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.score-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 20px;
}

.score-circle {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.score-value {
  font-size: 32px;
  font-weight: bold;
  color: white;
}

.score-total {
  font-size: 14px;
  color: rgba(255,255,255,0.8);
}

.score-label {
  margin-top: 8px;
  font-size: 14px;
  color: #666;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e3f2fd;
}

.dimensions-section {
  margin-bottom: 20px;
}

.dimension-item {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.dimension-name {
  width: 100px;
  font-size: 13px;
  color: #555;
}

.dimension-bar {
  flex: 1;
  height: 8px;
  background-color: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
  margin: 0 12px;
}

.dimension-fill {
  height: 100%;
  background: linear-gradient(90deg, #4caf50, #8bc34a);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.dimension-score {
  width: 50px;
  font-size: 13px;
  font-weight: 600;
  color: #1a73e8;
  text-align: right;
}

.comment-section {
  margin-bottom: 20px;
}

.overall-comment {
  font-size: 14px;
  line-height: 1.6;
  color: #555;
  background-color: #f8f9fa;
  padding: 12px;
  border-radius: 8px;
}

.improvements-section {
  margin-bottom: 20px;
}

.improvements-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.improvements-list li {
  padding: 10px 12px;
  background-color: #fff;
  border-left: 3px solid #4caf50;
  margin-bottom: 8px;
  border-radius: 0 4px 4px 0;
  font-size: 14px;
  color: #555;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.raw-response {
  margin-top: 16px;
  border-top: 1px solid #e0e0e0;
  padding-top: 12px;
}

.raw-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 8px 0;
  color: #666;
  font-size: 13px;
}

.toggle-icon {
  font-size: 12px;
}

.raw-content {
  padding: 12px;
  background-color: #f5f5f5;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

/* 错误提示弹窗 */
.error-toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  animation: slideDown 0.3s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

.error-content {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background-color: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  border-left: 4px solid #f44336;
}

.error-icon {
  font-size: 20px;
}

.error-text {
  font-size: 14px;
  color: #333;
}

.error-close {
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.error-close:hover {
  background-color: #f0f0f0;
  color: #666;
}

/* 输入区域 */
.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.char-count {
  font-size: 12px;
  color: #999;
}

/* 作文提交样式 */
.message.user.essay_submission {
  background-color: #fff3e0;
  border: 1px solid #ffcc80;
}

.message.user.essay_submission .message-content {
  font-style: italic;
  color: #666;
}

/* 历史记录 */
.history-group {
  margin-bottom: 12px;
}

.history-item {
  padding: 8px 12px;
  border-radius: 4px;
  background-color: #fff;
  text-align: left;
  margin-bottom: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-item:hover {
  background-color: #f8f9fa;
}

.history-item.active {
  background-color: #e3f2fd;
  color: #1a73e8;
}
</style>