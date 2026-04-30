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
        
        <!-- 对话历史 -->
        <div class="history-section">
          <!-- <div class="history-time">今天</div>
          <div class="history-item">AI批改教师页面提示词</div>
          
          <div class="history-time">昨天</div>
          <div class="history-item">OFD格式转换方法</div>
          
          <div class="history-time">7天内</div>
          <div class="history-item">考研院校专业咨询引导</div>
          <div class="history-item">软件测试师角色切换</div>
          <div class="history-item">逻辑回归代码解释与讨论</div>
          <div class="history-item">机器学习专家交流邀请</div>
          <div class="history-item">Git推送代码到GitHub教程</div>
          
          <div class="history-time">30天内</div>
          <div class="history-item">解决ReactAgent系统提示错误</div> -->
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
          
          <!-- 添加 loading 显示 -->
          <div v-if="isLoading" class="loading">
            <span class="loading-dot">.</span>
            <span class="loading-dot">.</span>
            <span class="loading-dot">.</span>
          </div>
        </div>
        
        <!-- 对话历史 -->
        <div class="chat-history" v-else ref="chatChontainer">
          <div class="message" v-for="(msg, index) in messages" :key="index" :class="msg.role">
            {{ msg.content }}
          </div>

          <!-- 加载状态 -->
          <div v-if="isLoading" class="loading">
            <span class="loading-dot">.</span>
            <span class="loading-dot">.</span>
            <span class="loading-dot">.</span>
          </div>
        </div>
        
        <!-- 输入区域 - 移到最外层 -->
        <div class="input-area">
          <textarea 
            class="input-textarea" 
            placeholder="给AI智能批改教师发送消息..." 
            v-model="inputText"
            @input="updateCharCount"
            maxlength="200"
          ></textarea>
          <button class="send-btn" @click="sendMessage">
            <span class="send-icon">↑</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import axios from 'axios';

// 状态管理
const messages = ref([]);
const inputText = ref('');
const charCount = ref(0);

//消息加载状态
const isLoading = ref(false)

const isSidebarOpen = ref(true)

// 对话历史容器
const chatChontainer = ref(null)

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value;
};

// 初始化
onMounted(() => {
  updateCharCount();
});

// 新建对话
const newChat = () => {
  messages.value = [];
  inputText.value = '';
  updateCharCount();
};

// 更新字数统计
const updateCharCount = () => {
  charCount.value = inputText.value.length;
};

// 发送消息
const sendMessage = async () => {
  if (!inputText.value.trim()) return;

  //设置加载状态
  isLoading.value = true
  
  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: inputText.value
  });
  
  // 滚动到最新消息
  if (chatChontainer.value) {
    chatChontainer.value.scrollTop = chatChontainer.value.scrollHeight;
  }
  
  // 清空输入框
  const message = inputText.value;
  inputText.value = '';
  updateCharCount();
  
  try {
    // 调用后端API
    const response = await axios.post('/api/chat', {
      message: message
    });
    
    // 添加AI回复
    messages.value.push({
      role: 'assistant',
      content: response.data
    });
  } catch (error) {
    console.error('API调用失败:', error);
    messages.value.push({
      role: 'assistant',
      content: '抱歉，处理请求时出现错误，请稍后重试。'
    });
  }
  finally {
    // 结束加载状态
    isLoading.value = false
  }
};

// 处理图片上传
const handleImageUpload = (event) => {
  const file = event.target.files[0];
  if (file) {
    console.log('上传图片:', file.name);
    // 这里可以添加图片上传逻辑
  }
};

// 处理文档上传
const handleDocUpload = (event) => {
  const file = event.target.files[0];
  if (file) {
    console.log('上传文档:', file.name);
    // 这里可以添加文档上传逻辑
  }
};
</script>

<style scoped>
/* 组件特定样式可以在这里添加 */
/* 添加加载动画样式 */
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
</style>