<template>
  <div class="type-selector">
    <!-- 年级：只保留年级选择，体裁由 AI 依据题干要求判定 -->
    <div class="selector-group">
      <span class="selector-label">年级</span>
      <div class="selector-options">
        <button
          v-for="option in gradeOptions"
          :key="option"
          type="button"
          class="ui-chip"
          :class="{ 'is-selected': grade === option }"
          :disabled="disabled"
          :title="`按${option}的评分要求批改`"
          @click="selectGrade(option)"
        >
          {{ option }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 年级选择组件
 *
 * 变更说明：
 * - 原「作文体裁 + 年级」中的体裁选择已移除：作文体裁不再由用户手动指定，
 *   改由 AI 依据作文题目与题干要求自动判定（题干明确限定体裁时严格按该体裁打分，
 *   未限定时按默认通用标准打分）。
 * - 年级保留，只影响批改时的评分尺度（由后端写入提示词），不改变评分维度。
 * - 复用公共样式 .ui-chip，与批改页保持一致。
 *
 * @props grade      当前年级
 * @props disabled   是否禁用
 * @event update:grade
 */

import { ref } from 'vue';

const props = defineProps({
  grade: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
});

const emit = defineEmits(['update:grade']);

// 年级选项（与后端 review_workbench.GRADES 保持一致）
const gradeOptions = ref(['七年级', '八年级', '九年级']);

/** 选择年级：再次点击已选项可取消 */
const selectGrade = (grade) => {
  if (props.disabled) return;
  emit('update:grade', props.grade === grade ? '' : grade);
};
</script>

<style scoped>
.type-selector {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 20px;
}

.selector-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-label {
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  white-space: nowrap;
}

.selector-options {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* 窄屏：标签换行后保持紧凑 */
@media (max-width: 600px) {
  .selector-group { gap: 6px; }
  .selector-options { gap: 4px; }
}
</style>
