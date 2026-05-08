<template>
  <div class="type-selector">
    <div class="type-selector-label">作文体裁</div>
    <div class="type-options">
      <button
        v-for="option in essayTypeOptions"
        :key="option.value"
        class="type-option"
        :class="{
          'selected': modelValue === option.value,
          'disabled': disabled
        }"
        @click="selectType(option.value)"
        :title="option.description"
      >
        <span class="type-icon">{{ option.icon }}</span>
        <span class="type-name">{{ option.label }}</span>
      </button>
    </div>
    <div v-if="!modelValue && showHint" class="type-hint">
      ⚠️ 请选择体裁
    </div>
  </div>
</template>

<script setup>
/**
 * 作文体裁选择组件
 * 
 * 提供三种作文体裁选项：议论文、记叙文、说明文
 * 用户可以选择其中一种作为作文批改的依据
 * 
 * 组件设计：
 * - 使用互斥选择模式，只能选择一种体裁
 * - 提供清晰的视觉反馈，选中状态有明显标识
 * - 支持禁用状态，在加载或提交时禁用选择
 * 
 * @props modelValue - 当前选中的体裁值
 * @props disabled - 是否禁用选择
 * @props showHint - 是否显示未选择提示
 * @event update:modelValue - 体裁选择变化时触发
 */

import { ref } from 'vue';

// 定义组件属性
const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  disabled: {
    type: Boolean,
    default: false
  },
  showHint: {
    type: Boolean,
    default: true
  }
});

// 定义事件
const emit = defineEmits(['update:modelValue']);

// 作文体裁选项配置
const essayTypeOptions = ref([
  {
    value: '议论文',
    label: '议论文',
    icon: '💬',
    description: '以议论为主，表达观点和论证'
  },
  {
    value: '记叙文',
    label: '记叙文',
    icon: '📖',
    description: '以叙述为主，讲述故事和经历'
  },
  {
    value: '说明文',
    label: '说明文',
    icon: '📝',
    description: '以说明为主，解释事物和原理'
  }
]);

/**
 * 选择体裁
 * 
 * @param {string} type - 体裁值
 */
const selectType = (type) => {
  if (props.disabled) return;
  
  // 如果点击已选中的选项，取消选择
  if (props.modelValue === type) {
    emit('update:modelValue', '');
  } else {
    emit('update:modelValue', type);
  }
};
</script>

<style scoped>
.type-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.type-selector-label {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.type-options {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.type-option {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background-color: #f8f9fa;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  color: #333;
}

.type-option:hover:not(.disabled):not(.selected) {
  background-color: #e9ecef;
  border-color: #d0d5dd;
}

.type-option.selected {
  background-color: #1a73e8;
  border-color: #1a73e8;
  color: white;
}

.type-option.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.type-icon {
  font-size: 14px;
}

.type-name {
  font-weight: 500;
}

.type-hint {
  font-size: 12px;
  color: #f59e0b;
  padding: 4px 8px;
  background-color: #fffbeb;
  border-radius: 4px;
  display: inline-block;
  width: fit-content;
}

/**
 * 响应式设计 - 平板设备 (768px以下)
 */
@media (max-width: 768px) {
  .type-option {
    padding: 6px 12px;
    font-size: 12px;
  }
  
  .type-icon {
    font-size: 12px;
  }
}

/**
 * 响应式设计 - 手机设备 (480px以下)
 */
@media (max-width: 480px) {
  .type-selector-label {
    font-size: 11px;
  }
  
  .type-options {
    gap: 6px;
  }
  
  .type-option {
    padding: 5px 10px;
    font-size: 11px;
    gap: 4px;
    border-radius: 16px;
  }
  
  .type-icon {
    font-size: 11px;
  }
  
  .type-hint {
    font-size: 11px;
    padding: 3px 6px;
  }
}

/**
 * 响应式设计 - 小屏手机 (320px以下)
 */
@media (max-width: 320px) {
  .type-option {
    padding: 4px 8px;
    font-size: 10px;
  }
  
  .type-icon {
    font-size: 10px;
  }
  
  .type-name {
    font-weight: 400;
  }
}

/**
 * 浏览器兼容性处理
 * 所有CSS属性在Chrome 90+、Firefox 88+、Safari 14+、Edge 90+中均支持
 */
</style>
