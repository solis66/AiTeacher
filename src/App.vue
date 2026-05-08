<template>
  <div id="app">
    <!-- 登录页面 -->
    <LoginPage
      v-if="!isLoggedIn"
      @login-success="handleLoginSuccess"
    />
    
    <!-- 主应用页面 -->
    <MainPage
      v-else
      @logout="handleLogout"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import LoginPage from './components/LoginPage.vue';
import MainPage from './components/MainPage.vue';

// 登录状态
const isLoggedIn = ref(false);

// 检查本地存储中是否有token
const checkAuthStatus = () => {
  const token = localStorage.getItem('ai_teacher_token');
  isLoggedIn.value = !!token;
};

// 处理登录成功
const handleLoginSuccess = (userInfo) => {
  console.log('登录成功:', userInfo);
  isLoggedIn.value = true;
};

// 处理登出
const handleLogout = () => {
  localStorage.removeItem('ai_teacher_token');
  localStorage.removeItem('ai_teacher_user');
  isLoggedIn.value = false;
};

// 页面加载时检查登录状态
onMounted(() => {
  checkAuthStatus();
});
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

#app {
  height: 100%;
}
</style>