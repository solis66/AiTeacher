<template>
  <Transition name="fade">
    <div v-if="isLoading" class="loading-container">
      <!-- 加载指示器 -->
      <div class="loading-spinner">
        <div class="spinner-ring"></div>
        <div class="spinner-inner"></div>
      </div>
      
      <!-- 加载文字 -->
      <span class="loading-text">{{ text }}</span>
    </div>
  </Transition>
</template>

<script setup>
/**
 * 简洁加载指示器组件
 * 
 * 功能说明：
 * 本组件提供一个轻量级的加载动画效果，用于在数据处理或网络请求期间向用户提供视觉反馈。
 * 
 * 设计特点：
 * 1. 紧凑的环形加载动画，不遮挡其他界面元素
 * 2. 简洁的文字提示，清晰传达处理状态
 * 3. 平滑的淡入淡出过渡效果
 * 4. 响应式设计，适配各种屏幕尺寸
 * 
 * @props isLoading - 是否显示加载动画
 * @props text - 加载提示文字
 */

defineProps({
  isLoading: {
    type: Boolean,
    default: false
  },
  text: {
    type: String,
    default: '处理中...'
  }
});
</script>

<style scoped>
/**
 * 加载容器
 */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px 24px;
  background-color: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

/**
 * 加载指示器
 */
.loading-spinner {
  position: relative;
  width: 32px;
  height: 32px;
}

.spinner-ring {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 3px solid var(--c-bg-muted);
  border-top-color: var(--c-primary);
  animation: spin 1s linear infinite;
}

.spinner-inner {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background-color: var(--c-primary);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    opacity: 0.6;
    transform: translate(-50%, -50%) scale(0.8);
  }
}

/**
 * 加载文字
 */
.loading-text {
  font-size: 14px;
  color: var(--c-text-secondary);
  font-weight: 500;
}

/**
 * 过渡动画
 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

/**
 * 响应式设计
 */
@media (max-width: 480px) {
  .loading-container {
    padding: 12px 20px;
  }
  
  .loading-spinner {
    width: 28px;
    height: 28px;
  }
  
  .loading-text {
    font-size: 13px;
  }
}
</style>
