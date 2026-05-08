<template>
  <div class="login-page">
    <!-- 背景装饰 -->
    <div class="login-bg">
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>
      <div class="bg-circle bg-circle-3"></div>
    </div>

    <!-- 登录卡片 -->
    <div class="login-card">
      <!-- Logo区域 -->
      <div class="login-header">
        <div class="logo-container">
          <span class="logo-icon">🎓</span>
          <h1 class="app-title">AI智能批改教师</h1>
        </div>
        <p class="app-subtitle">专业的初中作文批改助手</p>
      </div>

      <!-- 登录表单 -->
      <form class="login-form" @submit.prevent="handleSubmit">
        <!-- 用户名输入框 -->
        <div class="form-group">
          <label class="form-label">用户名</label>
          <div class="input-wrapper">
            <span class="input-icon">👤</span>
            <input
              type="text"
              v-model="form.username"
              class="form-input"
              placeholder="请输入用户名"
              autocomplete="username"
              @blur="validateUsername"
            />
          </div>
          <span v-if="errors.username" class="error-text">{{ errors.username }}</span>
        </div>

        <!-- 密码输入框（支持显示/隐藏切换） -->
        <div class="form-group">
          <label class="form-label">密码</label>
          <div class="input-wrapper">
            <span class="input-icon">🔒</span>
            <!-- 动态切换密码输入框类型：password/text -->
            <input
              :type="showPassword ? 'text' : 'password'"
              v-model="form.password"
              class="form-input"
              placeholder="请输入密码"
              autocomplete="current-password"
              @blur="validatePassword"
              @keydown.enter="handleSubmit"
            />
            <!-- 密码可见性切换按钮 -->
            <button
              type="button"
              class="toggle-password"
              @click="togglePasswordVisibility"
              :title="showPassword ? '隐藏密码' : '显示密码'"
            >
              {{ showPassword ? '🙈' : '👁️' }}
            </button>
          </div>
          <span v-if="errors.password" class="error-text">{{ errors.password }}</span>
        </div>

        <!-- 登录按钮 -->
        <button
          type="submit"
          class="login-button"
          :disabled="isLoading || !isFormValid"
        >
          <span v-if="isLoading" class="loading-spinner"></span>
          {{ isLoading ? '登录中...' : '登 录' }}
        </button>

        <!-- 登录错误提示 -->
        <div v-if="loginError" class="error-alert">
          <span class="alert-icon">⚠️</span>
          <span>{{ loginError }}</span>
        </div>

        <!-- 测试账号提示 -->
        <div class="hint-box">
          <p class="hint-text">测试账号：</p>
          <p class="hint-detail">用户名：admin</p>
          <p class="hint-detail">密码：123456</p>
        </div>
      </form>

      <!-- 页脚 -->
      <div class="login-footer">
        <p>© 2026 AI智能批改教师 | 让作文批改更专业</p>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 登录页面组件
 * 负责用户身份验证，包含用户名密码输入、表单验证、密码显示切换等功能
 * 
 * 核心功能：
 * 1. 表单验证（用户名非空、密码长度检查）
 * 2. 密码可见性切换
 * 3. JWT令牌获取与本地存储
 * 4. 登录状态管理与错误处理
 */
import { ref, computed, reactive } from 'vue';
import axios from 'axios';

/**
 * 后端API基础地址配置
 * 根据环境动态调整，前端调用需与后端接口路径一致
 * 后端登录接口路径: /login
 */
const API_BASE_URL = '/';

// 定义组件事件：登录成功时触发
const emit = defineEmits(['login-success']);

/**
 * 表单数据对象
 * 存储用户输入的用户名和密码
 */
const form = reactive({
  username: '',
  password: ''
});

/**
 * 状态管理变量
 * - isLoading: 登录请求加载状态
 * - showPassword: 密码是否显示（true=显示，false=隐藏）
 * - loginError: 登录错误信息
 * - errors: 表单字段验证错误
 */
const isLoading = ref(false);
const showPassword = ref(false);
const loginError = ref('');
const errors = reactive({
  username: '',
  password: ''
});

/**
 * 验证用户名输入
 * 检查用户名是否为空
 */
const validateUsername = () => {
  if (!form.username.trim()) {
    errors.username = '请输入用户名';
  } else {
    errors.username = '';
  }
};

/**
 * 验证密码输入
 * 检查密码是否为空以及长度是否不少于6位
 */
const validatePassword = () => {
  if (!form.password.trim()) {
    errors.password = '请输入密码';
  } else if (form.password.length < 6) {
    errors.password = '密码长度不能少于6位';
  } else {
    errors.password = '';
  }
};

/**
 * 计算属性：表单是否有效
 * 要求用户名和密码都非空，且没有验证错误
 */
const isFormValid = computed(() => {
  return form.username.trim() && form.password.trim() && !errors.username && !errors.password;
});

/**
 * 切换密码可见性
 * 切换showPassword状态，实现密码显示/隐藏功能
 */
const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value;
};

/**
 * 处理表单提交（登录请求）
 * 执行流程：
 * 1. 清除之前的错误信息
 * 2. 执行表单验证
 * 3. 如果表单无效，直接返回
 * 4. 发送登录请求到后端API
 * 5. 成功：保存token并触发登录成功事件
 * 6. 失败：显示错误信息
 */
const handleSubmit = async () => {
  // 清除之前的错误信息
  loginError.value = '';
  
  // 执行表单验证
  validateUsername();
  validatePassword();
  
  // 如果表单验证失败，不发送请求
  if (!isFormValid.value) {
    return;
  }

  // 设置加载状态
  isLoading.value = true;

  try {
    // 发送登录请求到后端
    // 后端接口路径: POST /login
    // 请求体: { username: string, password: string }
    // 返回: { success: boolean, token?: string, username?: string, error?: string }
    const response = await axios.post(`${API_BASE_URL}login`, {
      username: form.username.trim(),
      password: form.password.trim()
    });

    // 处理登录响应
    if (response.data.success) {
      // 保存JWT令牌到本地存储，用于后续API请求认证
      localStorage.setItem('ai_teacher_token', response.data.token);
      localStorage.setItem('ai_teacher_user', response.data.username);
      
      // 触发登录成功事件，通知父组件跳转主页面
      emit('login-success', {
        username: response.data.username,
        token: response.data.token
      });
    } else {
      // 登录失败（用户名或密码错误）
      loginError.value = response.data.error || '登录失败，请检查用户名和密码';
    }
  } catch (error) {
    // 捕获网络错误或服务器错误
    console.error('登录请求失败:', error);
    
    // 根据错误类型显示不同的错误信息
    if (error.response) {
      // 服务器返回错误（如404、500等）
      loginError.value = error.response.data?.error || `登录失败，服务器错误: ${error.response.status}`;
    } else if (error.request) {
      // 请求已发送但无响应（网络问题）
      loginError.value = '登录失败，请检查网络连接';
    } else {
      // 请求配置错误
      loginError.value = `登录失败: ${error.message}`;
    }
  } finally {
    // 无论成功或失败，都结束加载状态
    isLoading.value = false;
  }
};
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  position: relative;
  overflow: hidden;
}

/* 背景装饰 */
.login-bg {
  position: absolute;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.15;
}

.bg-circle-1 {
  width: 600px;
  height: 600px;
  background: #fff;
  top: -200px;
  right: -100px;
}

.bg-circle-2 {
  width: 400px;
  height: 400px;
  background: #fff;
  bottom: -150px;
  left: -50px;
}

.bg-circle-3 {
  width: 200px;
  height: 200px;
  background: #fff;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

/* 登录卡片 */
.login-card {
  position: relative;
  z-index: 10;
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  padding: 40px;
  animation: slideUp 0.5s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 头部区域 */
.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.logo-container {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 8px;
}

.logo-icon {
  font-size: 48px;
  animation: bounce 2s infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.app-title {
  font-size: 28px;
  font-weight: 700;
  color: #333;
  margin: 0;
}

.app-subtitle {
  font-size: 14px;
  color: #888;
  margin: 0;
}

/* 表单样式 */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 14px;
  font-size: 16px;
  color: #999;
}

.form-input {
  width: 100%;
  padding: 14px 14px 14px 45px;
  border: 2px solid #e0e0e0;
  border-radius: 10px;
  font-size: 16px;
  transition: all 0.3s ease;
  background: #fafafa;
}

.form-input:focus {
  outline: none;
  border-color: #667eea;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-input::placeholder {
  color: #bbb;
}

.toggle-password {
  position: absolute;
  right: 14px;
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #999;
  transition: all 0.3s ease;
  padding: 4px;
  border-radius: 50%;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.toggle-password:hover {
  color: #667eea;
  background-color: rgba(102, 126, 234, 0.1);
  transform: scale(1.1);
}

.toggle-password:active {
  transform: scale(0.95);
}

/* 错误提示 */
.error-text {
  font-size: 12px;
  color: #e74c3c;
}

.error-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #ffebee;
  border-radius: 8px;
  color: #c62828;
  font-size: 14px;
}

.alert-icon {
  font-size: 16px;
}

/* 登录按钮 */
.login-button {
  width: 100%;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.login-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
}

.login-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 加载动画 */
.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #fff;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 提示信息 */
.hint-box {
  background: #f8f9fa;
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}

.hint-text {
  font-size: 13px;
  color: #666;
  margin: 0 0 8px 0;
  font-weight: 500;
}

.hint-detail {
  font-size: 12px;
  color: #888;
  margin: 4px 0;
}

/* 页脚 */
.login-footer {
  text-align: center;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.login-footer p {
  font-size: 12px;
  color: #999;
  margin: 0;
}
</style>