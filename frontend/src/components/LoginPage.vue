<template>
  <div class="login-page">
    <!-- 登录卡片 -->
    <div class="login-card">
      <!-- Logo区域 -->
      <div class="login-header">
        <div class="logo-container">
          <div class="logo-icon">
            <GraduationCap :size="32" />
          </div>
          <h1 class="app-title">AI智能批改工作台</h1>
        </div>
        <p class="app-subtitle">专业的中学语文作文批改助手</p>
      </div>

      <!-- 登录/注册表单 -->
      <form class="login-form" @submit.prevent="handleSubmit">
        <!-- 账号（登录=用户名 / 注册=自定义账号）输入框 -->
        <div class="form-group">
          <label class="form-label">{{ mode === 'register' ? '账号' : '用户名' }}</label>
          <div class="input-wrapper">
            <span class="input-icon"><User :size="16" /></span>
            <input
              type="text"
              v-model="form.username"
              class="form-input"
              :placeholder="mode === 'register' ? '5~20位字母/数字/下划线' : '请输入用户名'"
              :maxlength="mode === 'register' ? 20 : undefined"
              autocomplete="username"
              @blur="validateUsername"
            />
          </div>
          <span v-if="errors.username" class="error-text">{{ errors.username }}</span>
        </div>

        <!-- 账号类型（仅注册时显示）：决定登录后可用的功能范围 -->
        <div v-if="mode === 'register'" class="form-group">
          <label class="form-label">账号类型</label>
          <div class="role-picker">
            <button
              v-for="opt in roleOptions"
              :key="opt.value"
              type="button"
              class="role-option"
              :class="{ 'is-active': form.role === opt.value }"
              @click="form.role = opt.value"
            >
              <component :is="opt.icon" :size="18" />
              <span class="role-name">{{ opt.label }}</span>
              <span class="role-desc">{{ opt.desc }}</span>
            </button>
          </div>
        </div>

        <!-- 密码输入框（支持显示/隐藏切换） -->
        <div class="form-group">
          <label class="form-label">密码</label>
          <div class="input-wrapper">
            <span class="input-icon"><Lock :size="16" /></span>
            <!-- 动态切换密码输入框类型：password/text -->
            <input
              :type="showPassword ? 'text' : 'password'"
              v-model="form.password"
              class="form-input"
              placeholder="请输入密码"
              :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
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
              <Eye v-if="!showPassword" :size="16" />
              <EyeOff v-else :size="16" />
            </button>
          </div>
          <span v-if="errors.password" class="error-text">{{ errors.password }}</span>
        </div>

        <!-- 确认密码输入框（仅注册时显示） -->
        <div v-if="mode === 'register'" class="form-group">
          <label class="form-label">确认密码</label>
          <div class="input-wrapper">
            <span class="input-icon"><Lock :size="16" /></span>
            <input
              :type="showPassword ? 'text' : 'password'"
              v-model="form.confirmPassword"
              class="form-input"
              placeholder="请再次输入密码"
              autocomplete="new-password"
              @blur="validateConfirmPassword"
              @keydown.enter="handleSubmit"
            />
          </div>
          <span v-if="errors.confirmPassword" class="error-text">{{ errors.confirmPassword }}</span>
        </div>

        <!-- 登录 / 注册按钮 -->
        <button
          type="submit"
          class="login-button"
          :disabled="isLoading || !isFormValid"
        >
          <Loader2 v-if="isLoading" :size="18" class="spin" />
          <template v-if="!isLoading">{{ mode === 'register' ? '注 册' : '登 录' }}</template>
          <template v-else>{{ mode === 'register' ? '注册中...' : '登录中...' }}</template>
        </button>

        <!-- 登录错误提示 -->
        <div v-if="loginError" class="alert error-alert">
          <AlertCircle :size="16" />
          <span>{{ loginError }}</span>
        </div>

        <!-- 登录/注册成功提示 -->
        <div v-if="successMessage" class="alert success-alert">
          <CheckCircle2 :size="16" />
          <span>{{ successMessage }}</span>
        </div>

        <!-- 模式切换 -->
        <div class="mode-switch">
          <span v-if="mode === 'login'">
            还没有账号？
            <button type="button" class="link-button" @click="switchMode('register')">立即注册</button>
          </span>
          <span v-else>
            已有账号？
            <button type="button" class="link-button" @click="switchMode('login')">返回登录</button>
          </span>
        </div>

        <!-- 测试账号提示（仅登录时显示） -->
        <div v-if="mode === 'login'" class="hint-box">
          <p class="hint-text">管理测试账号（老师）</p>
          <p class="hint-detail">账号：admin</p>
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
 * 负责用户身份验证，包含用户名密码输入、表单验证、密码显示切换等功能，
 * 并支持切换到注册模式（手机号+密码+确认密码）完成新用户注册。
 *
 * 核心功能：
 * 1. 登录：用户名（手机号）+ 密码，成功后保存 JWT 触发登录成功事件
 * 2. 注册：手机号 + 密码 + 确认密码，成功后回到登录页并预填手机号
 * 3. 表单验证（手机号格式、密码长度为6位、两次密码一致）
 * 4. 密码可见性切换
 */
import { ref, computed, reactive } from 'vue';
import {
  GraduationCap, User, Lock, Eye, EyeOff,
  Loader2, AlertCircle, CheckCircle2, Users
} from 'lucide-vue-next';
import request from '../api/request.js';
import { setToken, setUser, setRole } from '../utils/auth.js';

// 定义组件事件：登录成功时触发
const emit = defineEmits(['login-success']);

/** 登录模式 / 注册模式 */
const mode = ref('login');

/** 注册成功回到登录页时的提示 */
const successMessage = ref('');

/**
 * 表单数据对象
 * - username: 登录=用户名，注册=手机号（账户号码）
 * - password: 密码
 * - confirmPassword: 确认密码（仅注册）
 */
const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  role: 'student'
});

/**
 * 账号类型选项。
 * 用普通常量数组而非 reactive：选项里存的是组件对象，
 * 被响应式代理包住会让 Vue 报「组件被做成响应式」的警告。
 */
const roleOptions = [
  { value: 'student', label: '学生', desc: '加入班级、提交作文训练', icon: GraduationCap },
  { value: 'teacher', label: '老师', desc: '创建班级、发布作文、查看学情', icon: Users }
];

/**
 * 状态管理变量
 * - isLoading: 请求加载状态
 * - showPassword: 密码是否显示（true=显示，false=隐藏）
 * - loginError: 提交错误信息
 * - errors: 表单字段验证错误
 */
const isLoading = ref(false);
const showPassword = ref(false);
const loginError = ref('');
const errors = reactive({
  username: '',
  password: '',
  confirmPassword: ''
});

/**
 * 切换登录/注册模式
 * 切换时清空错误提示与表单，避免残留上个模式的状态
 */
const switchMode = (target) => {
  mode.value = target;
  loginError.value = '';
  successMessage.value = '';
  form.username = '';
  form.password = '';
  form.confirmPassword = '';
  errors.username = '';
  errors.password = '';
  errors.confirmPassword = '';
};

/**
 * 验证账号输入
 * 登录模式：非空即可；注册模式：必须是 11 位纯数字手机号
 */
const validateUsername = () => {
  const value = form.username.trim();
  if (!value) {
    errors.username = mode.value === 'register' ? '请输入账号' : '请输入用户名';
  } else if (mode.value === 'register' && !/^[A-Za-z0-9][A-Za-z0-9_]{4,19}$/.test(value)) {
    // 与后端 user_service.ACCOUNT_PATTERN 保持一致，避免前端放行、后端拒绝
    errors.username = '账号需为5~20位字母、数字或下划线，且以字母或数字开头';
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
 * 验证确认密码（注册模式）
 * 需与密码完全一致
 */
const validateConfirmPassword = () => {
  if (!form.confirmPassword) {
    errors.confirmPassword = '请再次输入密码';
  } else if (form.confirmPassword !== form.password) {
    errors.confirmPassword = '两次输入的密码不一致';
  } else {
    errors.confirmPassword = '';
  }
};

/**
 * 计算属性：表单是否有效
 * 登录模式要求账号密码有效；注册模式额外要求确认密码一致
 */
const isFormValid = computed(() => {
  const base = form.username.trim() && form.password.trim() &&
    !errors.username && !errors.password;
  if (mode.value === 'register') {
    return base && form.confirmPassword && !errors.confirmPassword;
  }
  return base;
});

/** 切换密码可见性 */
const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value;
};

/**
 * 提交注册请求
 * 校验通过后调用 POST /register，成功后切回登录模式并预填手机号
 */
/** 把角色值转成中文名，用于提示文案 */
const roleLabelOf = (value) => (roleOptions.find((o) => o.value === value)?.label || '');

const handleRegister = async () => {
  const response = await request.post('/register', {
    account: form.username.trim(),
    password: form.password.trim(),
    confirm_password: form.confirmPassword.trim(),
    role: form.role
  });

  if (response.data.success) {
    // 注册成功回登录页，携带提示并预填账号
    successMessage.value = `注册成功（${roleLabelOf(form.role) || '学生'}账号），请登录`;
    mode.value = 'login';
    form.password = '';
    form.confirmPassword = '';
    // 保留已注册的账号，方便用户直接登录
    errors.password = '';
    errors.confirmPassword = '';
    return;
  }
  // 注册失败，显示后端错误（如账号已注册、格式错误）
  loginError.value = response.data.error || response.data.message || '注册失败，请稍后重试';
};

/**
 * 处理表单提交（登录或注册）
 * 根据当前模式分发到登录/注册流程
 */
const handleSubmit = async () => {
  // 清除之前的错误信息
  loginError.value = '';

  // 执行表单验证
  validateUsername();
  validatePassword();
  if (mode.value === 'register') {
    validateConfirmPassword();
  }

  // 如果表单验证失败，不发送请求
  if (!isFormValid.value) {
    return;
  }

  // 设置加载状态
  isLoading.value = true;

  try {
    if (mode.value === 'register') {
      await handleRegister();
      return;
    }

    // 发送登录请求到后端
    // 后端接口路径: POST /login
    // 请求体: { username: string, password: string }
    // 返回: { success: boolean, token?: string, username?: string, error?: string }
    const response = await request.post('/login', {
      username: form.username.trim(),
      password: form.password.trim()
    });

    // 处理登录响应
    if (response.data.success) {
      // 保存JWT令牌与用户名到本地存储，用于后续API请求认证与数据归属
      setToken(response.data.token);
      setUser(response.data.username);
      // 账号类型：决定主界面显示老师端还是学生端入口（权限判定仍在服务端）
      setRole(response.data.role || '');

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
    console.error('请求失败:', error);

    // 根据错误类型显示不同的错误信息
    if (error.response) {
      // 服务器返回错误（如404、500等）
      loginError.value = error.response.data?.error || `请求失败，服务器错误: ${error.response.status}`;
    } else if (error.request) {
      // 请求已发送但无响应（网络问题）
      loginError.value = '请求失败，请检查网络连接';
    } else {
      // 请求配置错误
      loginError.value = `请求失败: ${error.message}`;
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
  padding: 24px;
  background-color: var(--c-bg);
}

/* 登录卡片 */
.login-card {
  width: 100%;
  max-width: 400px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: 36px;
  box-shadow: var(--shadow-2);
}

/* 头部区域 */
.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.logo-container {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 8px;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--r-md);
  background-color: var(--c-primary-soft);
  color: var(--c-primary);
}

.app-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--c-text);
  margin: 0;
  letter-spacing: -0.3px;
}

.app-subtitle {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  margin: 0;
}

/* 表单样式 */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text);
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 12px;
  display: flex;
  align-items: center;
  color: var(--c-text-muted);
}

.form-input {
  width: 100%;
  padding: 11px 12px 11px 40px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  font-size: var(--fs-md);
  color: var(--c-text);
  background-color: var(--c-surface);
  transition: border-color 0.15s, box-shadow 0.15s;
  outline: none;
}

.form-input:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(0, 117, 222, 0.12);
}

.form-input::placeholder {
  color: var(--c-text-muted);
}

.toggle-password {
  position: absolute;
  right: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  background: none;
  border: none;
  border-radius: var(--r-sm);
  color: var(--c-text-muted);
  cursor: pointer;
  transition: color 0.15s, background-color 0.15s;
}

.toggle-password:hover {
  color: var(--c-text-secondary);
  background-color: var(--c-bg-muted);
}

/* 错误提示 */
.error-text {
  font-size: var(--fs-xs);
  color: var(--c-error);
}

/* 账号类型选择：两个并排卡片，选中态用主色描边 + 浅底 */
.role-picker {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.role-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 12px;
  font-family: inherit;
  text-align: left;
  color: var(--c-text-secondary);
  background: var(--c-surface);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: border-color .15s, background-color .15s, color .15s;
}

.role-option:hover {
  border-color: var(--c-primary);
}

.role-option.is-active {
  color: var(--c-primary);
  background: var(--c-primary-soft);
  border-color: var(--c-primary);
}

.role-name {
  font-size: var(--fs-sm);
  font-weight: 600;
}

.role-desc {
  font-size: 11px;
  line-height: 1.4;
  color: var(--c-text-muted);
}

.role-option.is-active .role-desc {
  color: var(--c-primary);
  opacity: .8;
}

.alert {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--r-md);
  font-size: var(--fs-sm);
}

.error-alert {
  color: var(--c-error);
  background-color: var(--c-error-soft);
  border: 1px solid rgba(217, 48, 37, 0.12);
}

.success-alert {
  color: var(--c-ok);
  background-color: var(--c-ok-soft);
  border: 1px solid rgba(26, 127, 55, 0.12);
}

/* 登录/注册模式切换 */
.mode-switch {
  text-align: center;
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
}

.link-button {
  background: none;
  border: none;
  padding: 0;
  font-size: var(--fs-sm);
  color: var(--c-primary);
  cursor: pointer;
  font-weight: 600;
}

.link-button:hover {
  text-decoration: underline;
}

/* 登录按钮 */
.login-button {
  width: 100%;
  padding: 12px;
  background-color: var(--c-primary);
  color: #fff;
  border: none;
  border-radius: var(--r-md);
  font-size: var(--fs-md);
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.login-button:hover:not(:disabled) {
  background-color: var(--c-primary-hover);
}

.login-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 加载动画 */
.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 提示信息 */
.hint-box {
  background-color: var(--c-bg-subtle);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  padding: 14px;
  text-align: center;
}

.hint-text {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--c-text-secondary);
  margin: 0 0 8px 0;
}

.hint-detail {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  margin: 3px 0;
}

/* 页脚 */
.login-footer {
  text-align: center;
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid var(--c-border);
}

.login-footer p {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  margin: 0;
}

@media (max-width: 480px) {
  .login-card {
    padding: 28px 24px;
  }
}
</style>
