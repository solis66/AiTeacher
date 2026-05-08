<template>
  <div class="input-area">
    <!-- 体裁选择区域 -->
    <div class="input-type-selector">
      <TypeSelector 
        v-model="localEssayType" 
        :disabled="isLoading"
        @update:model-value="handleTypeChange"
      />
    </div>
    
    <!-- 输入框 -->
    <textarea
      ref="textareaRef"
      v-model="inputContent"
      class="input-textarea"
      :placeholder="placeholder"
      :disabled="isLoading"
      @keydown.ctrl.enter="handleSend"
      @keydown.meta.enter="handleSend"
    ></textarea>
    
    <!-- 图片预览 -->
    <div v-if="imagePreview" class="image-preview">
      <img :src="imagePreview" alt="预览" />
      <button class="remove-image-btn" @click="removeImage">×</button>
    </div>
    
    <!-- 底部操作栏 -->
    <div class="input-footer">
      <div class="input-left">
        <!-- 文件上传按钮 -->
        <label class="upload-btn" :disabled="isLoading">
          <span class="upload-icon">📁</span>
          <span>上传文件</span>
          <input 
            type="file" 
            class="file-input" 
            accept="image/*,.txt,.docx"
            @change="handleFileUpload"
            :disabled="isLoading"
          />
        </label>
        
        <!-- 快捷键提示 -->
        <span class="shortcut-hint">Ctrl + Enter 发送</span>
      </div>
      
      <div class="input-right">
        <!-- 字数统计 -->
        <span class="char-count">{{ inputContent.length }}/{{ maxLength }}</span>
        
        <!-- 发送按钮 -->
        <button 
          class="send-btn" 
          :disabled="!canSend || isLoading"
          @click="handleSend"
        >
          <span class="send-icon">{{ isLoading ? '⏳' : '→' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 输入区域组件
 * 
 * 负责用户作文输入，提供以下功能：
 * - 文本输入（支持字数统计和限制）
 * - 作文体裁选择
 * - 文件上传（图片、文本、Word文档）
 * - 快捷键支持（Ctrl+Enter发送）
 * - 加载状态管理
 * 
 * 组件设计：
 * - 响应式布局，适配不同屏幕尺寸
 * - 清晰的视觉反馈（禁用状态、加载状态）
 * - 字数统计和限制提示
 * 
 * @props modelValue - 输入内容
 * @props essayType - 当前选中的体裁
 * @props isLoading - 是否正在加载
 * @props maxLength - 最大输入字数
 * @props placeholder - 输入占位符
 * @event update:modelValue - 内容变化时触发
 * @event update:essayType - 体裁变化时触发
 * @event send - 发送消息时触发
 * @event file-upload - 文件上传时触发
 */

import { ref, computed, watch } from 'vue';
import TypeSelector from './TypeSelector.vue';

// 定义组件属性
const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  essayType: {
    type: String,
    default: ''
  },
  isLoading: {
    type: Boolean,
    default: false
  },
  maxLength: {
    type: Number,
    default: 5000
  },
  placeholder: {
    type: String,
    default: '输入作文内容进行批改...'
  }
});

// 定义事件
const emit = defineEmits(['update:modelValue', 'update:essayType', 'send', 'file-upload']);

// 本地状态
const inputContent = ref(props.modelValue);
const localEssayType = ref(props.essayType);
const imagePreview = ref(null);
const textareaRef = ref(null);

// 监听外部内容变化
watch(
  () => props.modelValue,
  (newValue) => {
    inputContent.value = newValue;
  }
);

// 监听外部体裁变化
watch(
  () => props.essayType,
  (newValue) => {
    localEssayType.value = newValue;
  }
);

/**
 * 是否可以发送
 */
const canSend = computed(() => {
  const content = inputContent.value.trim();
  return content.length > 0 && content.length <= props.maxLength && !props.isLoading;
});

/**
 * 处理体裁变化
 * 
 * @param {string} type - 体裁值
 */
const handleTypeChange = (type) => {
  localEssayType.value = type;
  emit('update:essayType', type);
};

/**
 * 处理文件上传
 * 
 * @param {Event} event - 文件选择事件
 */
const handleFileUpload = (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  
  const reader = new FileReader();
  
  if (file.type.startsWith('image/')) {
    reader.onload = (e) => {
      imagePreview.value = e.target?.result;
      emit('file-upload', { file, type: 'image', data: e.target?.result });
    };
    reader.readAsDataURL(file);
  } else {
    reader.onload = (e) => {
      const content = e.target?.result;
      if (content && typeof content === 'string') {
        inputContent.value += content.substring(0, props.maxLength - inputContent.value.length);
        emit('file-upload', { file, type: 'text', data: content });
      }
    };
    reader.readAsText(file, 'utf-8');
  }
  
  // 重置文件输入
  event.target.value = '';
};

/**
 * 移除图片
 */
const removeImage = () => {
  imagePreview.value = null;
};

/**
 * 处理发送
 */
const handleSend = () => {
  if (!canSend.value) return;
  
  emit('send', {
    content: inputContent.value,
    essayType: localEssayType.value
  });
  
  // 清空输入
  inputContent.value = '';
  imagePreview.value = null;
};
</script>

<style scoped>
/**
 * 输入区域容器样式
 * 
 * 设计思路：
 * 1. 使用relative定位替代absolute，使其保持在文档流中
 * 2. 通过margin-top:auto实现底部固定效果
 * 3. 设置z-index确保层级正确
 * 4. 添加margin-top: 10px确保与聊天内容保持安全距离
 * 
 * 响应式设计：
 * - 默认宽度：calc(100% - 40px)，最大900px
 * - 平板(<768px)：宽度自适应，减少内边距
 * - 手机(<480px)：宽度95%，进一步精简
 */
.input-area {
  /* 定位方式：使用relative保持在文档流中，避免absolute导致的遮挡问题 */
  position: relative;
  
  /* 尺寸设置 */
  width: calc(100% - 40px);
  max-width: 900px;
  
  /* 外边距：顶部10px安全距离，左右居中，底部20px */
  margin: 10px auto 20px auto;
  
  /* 内边距 */
  padding: 16px;
  
  /* 背景与边框 */
  background-color: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  
  /* 阴影效果 */
  box-shadow: 0 2px 15px rgba(0, 0, 0, 0.1);
  
  /* 层级设置：确保在聊天内容之上但不遮挡 */
  z-index: 10;
  
  /* 盒模型 */
  box-sizing: border-box;
  
  /* 防止被压缩 */
  flex-shrink: 0;
}

/* 体裁选择区域 */
.input-type-selector {
  margin-bottom: 12px;
}

/* 输入框样式 */
.input-textarea {
  width: 100%;
  min-height: 80px;
  max-height: 200px;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  resize: vertical;
  font-family: inherit;
  font-size: 14px;
  margin-bottom: 10px;
  box-sizing: border-box;
  line-height: 1.5;
}

.input-textarea:focus {
  outline: none;
  border-color: #1a73e8;
  box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.2);
}

.input-textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  background-color: #f5f5f5;
}

/* 图片预览区域 */
.image-preview {
  position: relative;
  max-width: 200px;
  max-height: 150px;
  margin-bottom: 10px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  overflow: hidden;
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.remove-image-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-color: rgba(0, 0, 0, 0.6);
  color: white;
  border: none;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s;
}

.remove-image-btn:hover {
  background-color: rgba(0, 0, 0, 0.8);
}

/* 底部操作栏 */
.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.input-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.input-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 文件上传按钮 */
.upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background-color: #f8f9fa;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  color: #333;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  margin-left: 0;
}

.upload-btn:hover:not(:disabled) {
  background-color: #e9ecef;
  border-color: #d0d5dd;
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-icon {
  font-size: 14px;
}

.file-input {
  display: none;
}

/* 快捷键提示 */
.shortcut-hint {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

/* 字数统计 */
.char-count {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

/* 发送按钮 */
.send-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-color: #1a73e8;
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background-color: #1557b0;
}

.send-btn:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

.send-icon {
  font-size: 16px;
  font-weight: bold;
}

/**
 * 响应式设计 - 平板设备 (768px以下)
 * 
 * 调整策略：
 * 1. 保持宽度自适应
 * 2. 隐藏快捷键提示节省空间
 * 3. 调整按钮尺寸
 */
@media (max-width: 768px) {
  .input-area {
    width: calc(100% - 32px);
    padding: 12px;
    margin: 8px auto 16px auto;
  }
  
  .input-textarea {
    min-height: 70px;
    font-size: 16px; /* 防止iOS缩放 */
  }
  
  .shortcut-hint {
    display: none;
  }
  
  .upload-btn {
    padding: 6px 12px;
    font-size: 12px;
  }
}

/**
 * 响应式设计 - 手机设备 (480px以下)
 * 
 * 调整策略：
 * 1. 更宽的宽度比例(95%)
 * 2. 更小的内边距
 * 3. 更紧凑的按钮
 */
@media (max-width: 480px) {
  .input-area {
    width: 95%;
    padding: 10px;
    margin: 6px auto 12px auto;
    border-radius: 10px;
  }
  
  .input-textarea {
    min-height: 60px;
    padding: 10px;
    font-size: 16px;
  }
  
  .upload-btn {
    padding: 4px 8px;
    font-size: 11px;
    margin-left: 0;
  }
  
  .upload-icon {
    font-size: 12px;
  }
  
  .input-left {
    gap: 4px;
  }
  
  .input-footer {
    gap: 6px;
  }
}

/**
 * 响应式设计 - 小屏手机 (320px以下)
 * 
 * 调整策略：
 * 1. 全宽显示
 * 2. 最小化内边距
 */
@media (max-width: 320px) {
  .input-area {
    width: 98%;
    padding: 8px;
    margin: 4px auto 8px auto;
  }
  
  .input-textarea {
    min-height: 50px;
    padding: 8px;
  }
  
  .upload-btn span:last-child {
    display: none; /* 隐藏"上传文件"文字，只显示图标 */
  }
}

/**
 * 响应式设计 - 大屏桌面 (1440px以上)
 * 
 * 调整策略：
 * 1. 增加最大宽度限制
 * 2. 增加内边距提升视觉舒适度
 */
@media (min-width: 1440px) {
  .input-area {
    max-width: 1000px;
    padding: 20px;
  }
  
  .input-textarea {
    min-height: 100px;
  }
}

/**
 * 响应式设计 - 超大屏 (1920px以上)
 * 
 * 调整策略：
 * 1. 进一步增加最大宽度
 * 2. 增加字体大小提升可读性
 */
@media (min-width: 1920px) {
  .input-area {
    max-width: 1200px;
  }
  
  .input-textarea {
    font-size: 15px;
  }
}

/**
 * 浏览器兼容性处理
 * 
 * 1. Safari 14+ 支持所有使用的CSS属性
 * 2. Chrome 90+、Firefox 88+、Edge 90+ 完全支持
 * 3. 使用标准的CSS属性，无需额外前缀
 */

/* 确保在旧版浏览器中flex布局正常 */
@supports not (display: flex) {
  .input-footer {
    display: block;
  }
  
  .input-left,
  .input-right {
    display: inline-block;
  }
}

/* 打印样式优化 */
@media print {
  .input-area {
    display: none;
  }
}
</style>
