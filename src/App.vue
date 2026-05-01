<template>
  <div class="app">
    <div class="main-container" :class="{'sidebar-collapsed': !isSidebarOpen}">
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

        <!-- 开启新对话按钮 -->
        <button class="new-chat-btn" @click="newChat">
          <span class="new-chat-icon">+</span> 新对话
        </button>

        <!-- 对话历史列表 -->
        <div class="history-section">
          <div v-for="(chat, idx) in chatHistory" :key="idx" class="history-group">
            <div class="history-time">{{ chat.displayDate || formatDate(chat.date) }}</div>
            <div
              v-for="(msg, msgIdx) in chat.messages.slice(0, 1)"
              :key="msgIdx"
              class="history-item"
              :class="{'active': currentChatId === chat.id}"
              @click="loadChat(chat.id)"
            >
              {{ msg.content.substring(0, 20) }}{{ msg.content.length > 20 ? '...' : '' }}
            </div>
          </div>
        </div>

        <!-- 用户信息 -->
        <div class="user-info-sidebar">
          <div class="avatar">M</div>
          <div class="user-details">
            <div class="user-name">MOMO</div>
          </div>
        </div>
      </div>

      <!-- 主内容区域 -->
      <div class="main-content">
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
            @keydown.enter.ctrl="sendMessage"
            maxlength="5000"
          ></textarea>
          <div class="input-footer">
            <span class="char-count">{{ charCount }}/5000</span>
            <button class="send-btn" @click="sendMessage" :disabled="isLoading || !inputText.trim()">
              <span class="send-icon">↑</span>
            </button>
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
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue';
import axios from 'axios';

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

const STORAGE_KEY = 'ai_teacher_chat_history';
const MAX_HISTORY = 50;

const essayKeywords = ['作文', '文章', '写作', ' essay', '作文题', '请批改', '请点评', '写一篇', '写了一篇', '字数', '段落', '开头', '结尾', '议论文', '记叙文', '说明文'];
const consultationKeywords = ['如何', '怎么', '怎样', '为什么', '请问', '我想问', '问一下', '咨询', '方法', '技巧', '策略', '要点', '建议'];

const isEssaySubmission = (text) => {
  const hasEssayKeywords = essayKeywords.some(kw => text.includes(kw));
  const hasConsultKeywords = consultationKeywords.some(kw => text.includes(kw));
  const isLongText = text.length > 200;

  if (hasEssayKeywords && !hasConsultKeywords) return true;
  if (hasConsultKeywords && !hasEssayKeywords) return false;
  return isLongText;
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

const formatDate = (dateStr) => {
  const { todayStr, yesterdayStr, todayDateStr } = getTodayDate();

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

  return todayDateStr;
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

const loadHistory = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    console.log('[loadHistory] localStorage 数据:', saved);
    if (saved) {
      const history = JSON.parse(saved);
      console.log('[loadHistory] 解析后的历史记录数量:', history.length);
      history.forEach((chat, idx) => {
        console.log(`[loadHistory] 对话${idx}: id=${chat.id}, date=${chat.date}, messagesCount=${chat.messages?.length || 0}`);
      });
      chatHistory.value = history
        .filter(chat => chat.messages && chat.messages.length > 0)
        .map(chat => ({
          ...chat,
          displayDate: formatDate(chat.date)
        }));
      console.log('[loadHistory] 过滤后的历史记录数量:', chatHistory.value.length);
      chatHistory.value.forEach((chat, idx) => {
        console.log(`[loadHistory] 最终对话${idx}: id=${chat.id}, date=${chat.date}, displayDate=${chat.displayDate}`);
      });
    }
  } catch (e) {
    console.error('加载历史记录失败:', e);
    chatHistory.value = [];
  }
};

const saveHistory = () => {
  try {
    const dataToSave = chatHistory.value.map(chat => ({
      id: chat.id,
      date: chat.date,
      messages: chat.messages
    }));

    if (dataToSave.length > MAX_HISTORY) {
      dataToSave.splice(0, dataToSave.length - MAX_HISTORY);
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
  } catch (e) {
    console.error('保存历史记录失败:', e);
  }
};

const createNewChat = (force = false) => {
  console.log('[createNewChat] force:', force);

  if (!force && messages.value.length === 0 && chatHistory.value.length > 0) {
    return currentChatId.value;
  }

  if (messages.value.length === 0 && chatHistory.value.length > 0) {
    const existingEmpty = chatHistory.value.find(c => c.id === currentChatId.value);
    if (existingEmpty) {
      messages.value = [];
      return currentChatId.value;
    }
  }

  const id = generateId();
  const { todayStr } = getTodayDate();

  console.log('[createNewChat] 创建新对话, todayStr:', todayStr);

  chatHistory.value.unshift({
    id,
    date: todayStr,
    displayDate: '今天',
    messages: []
  });

  currentChatId.value = id;
  messages.value = [];
  saveHistory();

  return id;
};

const newChat = () => {
  if (isCreatingChat.value) {
    console.log('[新对话] 正在创建对话中，跳过');
    return;
  }

  isCreatingChat.value = true;

  try {
    console.log('[新对话] 点击新对话按钮', {
      hasMessages: messages.value.length > 0,
      currentChatId: currentChatId.value,
      historyLength: chatHistory.value.length
    });

    if (messages.value.length > 0) {
      console.log('[新对话] 保存当前对话');
      saveCurrentChat();
      console.log('[新对话] 创建新对话');
      createNewChat(true);
    } else {
      console.log('[新对话] 当前无消息，检查是否需要创建');
      if (chatHistory.value.length === 0) {
        console.log('[新对话] 历史为空，创建新对话');
        createNewChat(true);
      } else {
        console.log('[新对话] 已有对话，不创建新对话');
      }
    }
  } finally {
    isCreatingChat.value = false;
  }

  inputText.value = '';
  updateCharCount();
  expandedSections.value = {};
};

const saveCurrentChat = () => {
  if (!currentChatId.value || messages.value.length === 0) return;

  const chatIndex = chatHistory.value.findIndex(c => c.id === currentChatId.value);
  if (chatIndex !== -1) {
    chatHistory.value[chatIndex].messages = [...messages.value];
    chatHistory.value[chatIndex].displayDate = formatDate(chatHistory.value[chatIndex].date);
    saveHistory();
  }
};

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

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value;
};

onMounted(() => {
  loadHistory();
  refreshDisplayDates();
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

  updateCharCount();
});

onUnmounted(() => {
  stopDateCheckTimer();
});

const updateCharCount = () => {
  charCount.value = inputText.value.length;
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

const sendMessage = async () => {
  if (!inputText.value.trim()) return;

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

const handleImageUpload = (event) => {
  const file = event.target.files[0];
  if (file) {
    console.log('上传图片:', file.name);
  }
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