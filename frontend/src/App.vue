<template>
  <div class="app-root">
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
import { getToken, clearAuth } from './utils/auth.js';

// 登录状态
const isLoggedIn = ref(false);

/** 检查本地存储中是否有 token，有则直接进入主页面 */
const checkAuthStatus = () => {
  isLoggedIn.value = !!getToken();
};

// 处理登录成功
const handleLoginSuccess = (userInfo) => {
  console.log('登录成功:', userInfo);
  isLoggedIn.value = true;
};

/** 处理登出：清除本地登录态并回到登录页 */
const handleLogout = () => {
  clearAuth();
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
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Roboto, 'Helvetica Neue', Arial, sans-serif;
  color: var(--c-text);
  background-color: var(--c-bg);
}

/*
 * 高度链：#app（index.html 挂载点）→ .app-root（本组件根节点）都必须撑满，
 * 否则子页面的 height:100% 会退化成内容高度，滚动容器失效、底部内容被裁掉。
 *
 * 注意：这里曾把根节点也写成 id="app"，与 index.html 的挂载点形成重复 ID，
 * 属于非法 DOM，会让高度规则命中两层不同节点，故改为 class。
 */
#app {
  height: 100%;
}

.app-root {
  height: 100%;
}
</style>