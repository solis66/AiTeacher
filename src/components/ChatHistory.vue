<template>
  <div class="chat-history" ref="chatHistoryRef">
    <div
      v-for="(msg, index) in messages"
      :key="msg.id || index"
      class="message"
      :class="{
        'user': msg.role === 'user',
        'assistant': msg.role === 'assistant'
      }"
    >
      <!-- 用户头像 -->
      <div class="message-avatar">
        {{ msg.role === 'user' ? '👤' : '🤖' }}
      </div>
      
      <!-- 消息内容 -->
      <div class="message-content-wrapper">
        <div class="message-header">
          <span class="message-role">{{ msg.role === 'user' ? '我' : 'AI批改老师' }}</span>
          <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
        </div>
        
        <!-- 普通消息内容（非作文批改时显示） -->
        <div v-if="!(msg.data && isEssayReview(msg.data))" class="message-content">
          {{ msg.content }}
        </div>
        
        <!-- 图片预览 -->
        <div v-if="msg.image" class="message-image">
          <img 
            :src="msg.image" 
            class="preview-img" 
            alt="图片"
            @click="previewImage(msg.image)"
          />
        </div>
        
        <!-- 作文批改结果（替换原始文本显示） -->
        <EssayReview 
          v-if="msg.data && isEssayReview(msg.data)" 
          :review-data="msg.data" 
        />
      </div>
      
      <!-- 消息状态 -->
      <div v-if="msg.role === 'assistant' && msg.status" class="message-status">
        <span v-if="msg.status === 'loading'" class="status-loading">⏳ 思考中...</span>
        <span v-else-if="msg.status === 'error'" class="status-error">❌ 出错了</span>
      </div>
    </div>
    
    <!-- 空状态提示 -->
    <div v-if="messages.length === 0" class="empty-state">
      <div class="empty-icon">📝</div>
      <div class="empty-title">开始你的作文批改之旅</div>
      <div class="empty-desc">输入作文内容，AI批改老师将为您提供专业的批改服务</div>
    </div>
  </div>
</template>

<script setup>
/**
 * 对话历史组件
 * 
 * 负责展示对话历史记录，包括：
 * - 用户和AI的消息列表
 * - 消息状态（加载中、成功、失败）
 * - 作文批改结果展示
 * - 图片预览功能
 * - 空状态提示
 * 
 * 功能特性：
 * - 自动滚动到底部
 * - 支持图片预览
 * - 区分用户和AI消息样式
 * - 空状态友好提示
 * 
 * @props messages - 消息列表
 * @event preview-image - 点击图片时触发预览
 */

import { ref, watch, nextTick } from 'vue';
import EssayReview from './EssayReview.vue';

// 定义组件属性
const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  }
});

// 定义事件
const emit = defineEmits(['preview-image']);

// 聊天历史容器引用
const chatHistoryRef = ref(null);

/**
 * 判断是否为作文批改结果
 * 
 * @param {Object} data - 消息数据
 * @returns {boolean} - 是否为作文批改结果
 */
const isEssayReview = (data) => {
  return data.score !== null || data.dimensions?.length > 0;
};

/**
 * 格式化时间戳
 * 
 * @param {number} timestamp - 时间戳
 * @returns {string} - 格式化的时间字符串
 */
const formatTime = (timestamp) => {
  if (!timestamp) return '';
  
  const date = new Date(timestamp);
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  
  return `${hours}:${minutes}`;
};

/**
 * 预览图片
 * 
 * @param {string} imageUrl - 图片URL
 */
const previewImage = (imageUrl) => {
  emit('preview-image', imageUrl);
};

/**
 * 滚动到底部
 */
const scrollToBottom = async () => {
  await nextTick();
  if (chatHistoryRef.value) {
    chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight;
  }
};

// 监听消息变化，自动滚动到底部
watch(
  () => props.messages.length,
  () => {
    scrollToBottom();
  }
);
</script>

<style scoped>
/**
 * 聊天历史容器样式
 * 
 * 设计思路：
 * 1. 使用flex:1占据主内容区域的剩余空间
 * 2. 移除padding-bottom（InputArea已改为relative定位，不再遮挡）
 * 3. 保持overflow-y:auto实现消息过多时滚动
 * 4. min-height:0确保flex子元素可以正确收缩
 * 
 * 响应式设计：
 * - 默认：padding 20px
 * - 平板(<768px)：padding减少到16px
 * - 手机(<480px)：padding减少到12px
 */
.chat-history {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  /* 滚动行为优化 */
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch; /* iOS平滑滚动 */
}

.message {
  display: flex;
  gap: 12px;
  max-width: 70%;
  margin-bottom: 16px;
}

.message.user {
  margin-left: auto;
  margin-right: 0;
}

.message.assistant {
  margin-left: 0;
  margin-right: auto;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-color: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background-color: #1a73e8;
  color: white;
}

.message-content-wrapper {
  flex: 1;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.message-role {
  font-size: 12px;
  font-weight: 600;
  color: #666;
}

.message-time {
  font-size: 11px;
  color: #999;
}

.message-content {
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.message.user .message-content {
  background-color: #e3f2fd;
  border-bottom-right-radius: 2px;
}

.message.assistant .message-content {
  background-color: #fff;
  border-bottom-left-radius: 2px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

/* 图片预览 */
.message-image {
  margin-top: 8px;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
}

.preview-img {
  width: 120px;
  height: auto;
  display: block;
  border-radius: 8px;
  transition: transform 0.2s;
}

.preview-img:hover {
  transform: scale(1.02);
}

/* 消息状态 */
.message-status {
  margin-top: 4px;
  padding-left: 48px;
}

.status-loading {
  font-size: 12px;
  color: #1a73e8;
}

.status-error {
  font-size: 12px;
  color: #e74c3c;
}

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 20px;
}

.empty-title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
}

.empty-desc {
  font-size: 14px;
  color: #666;
  line-height: 1.5;
}

/**
 * 响应式设计 - 平板设备 (768px以下)
 */
@media (max-width: 768px) {
  .chat-history {
    padding: 16px;
  }
  
  .message {
    max-width: 85%;
    gap: 10px;
    margin-bottom: 14px;
  }
  
  .message-avatar {
    width: 32px;
    height: 32px;
    font-size: 14px;
  }
  
  .message-content {
    padding: 10px 14px;
    font-size: 13px;
  }
  
  .empty-state {
    padding: 30px;
  }
  
  .empty-icon {
    font-size: 40px;
  }
  
  .empty-title {
    font-size: 18px;
  }
}

/**
 * 响应式设计 - 手机设备 (480px以下)
 */
@media (max-width: 480px) {
  .chat-history {
    padding: 12px;
  }
  
  .message {
    max-width: 90%;
    gap: 8px;
    margin-bottom: 12px;
  }
  
  .message-avatar {
    width: 28px;
    height: 28px;
    font-size: 12px;
  }
  
  .message-header {
    gap: 6px;
    margin-bottom: 3px;
  }
  
  .message-role {
    font-size: 11px;
  }
  
  .message-time {
    font-size: 10px;
  }
  
  .message-content {
    padding: 8px 12px;
    font-size: 13px;
    line-height: 1.4;
  }
  
  .preview-img {
    width: 100px;
  }
  
  .message-status {
    padding-left: 36px;
  }
  
  .empty-state {
    padding: 20px;
  }
  
  .empty-icon {
    font-size: 36px;
    margin-bottom: 16px;
  }
  
  .empty-title {
    font-size: 16px;
    margin-bottom: 8px;
  }
  
  .empty-desc {
    font-size: 13px;
  }
}

/**
 * 响应式设计 - 小屏手机 (320px以下)
 */
@media (max-width: 320px) {
  .chat-history {
    padding: 8px;
  }
  
  .message {
    max-width: 95%;
    gap: 6px;
    margin-bottom: 10px;
  }
  
  .message-avatar {
    width: 24px;
    height: 24px;
    font-size: 10px;
  }
  
  .message-content {
    padding: 6px 10px;
    font-size: 12px;
  }
  
  .preview-img {
    width: 80px;
  }
  
  .message-status {
    padding-left: 30px;
  }
}

/**
 * 浏览器兼容性处理
 * 所有CSS属性在Chrome 90+、Firefox 88+、Safari 14+、Edge 90+中均支持
 */

/* 打印样式优化 */
@media print {
  .chat-history {
    overflow-y: visible;
    padding-bottom: 20px;
  }
  
  .message {
    break-inside: avoid;
  }
}
</style>
