<template>
  <div class="essay-review">
    <!-- 标题区域 -->
    <div class="review-header">
      <span class="review-title">📝 作文批改结果</span>
      <span class="essay-type-badge">{{ reviewData.essayType }}</span>
    </div>

    <!-- 总分显示 -->
    <div v-if="reviewData.score !== null && reviewData.score !== undefined" class="score-section">
      <div class="score-circle" :class="getTotalScoreLevel(reviewData.score, reviewData.totalScore)">
        <span class="score-value">{{ reviewData.score }}</span>
        <span class="score-total">/{{ reviewData.totalScore }}</span>
      </div>
      <div class="score-label">总分</div>
      <!-- 总分校验警告 -->
      <div v-if="!isScoreConsistent && dimensionsSum > 0" class="score-warning">
        <span class="warning-icon">⚠️</span>
        <span class="warning-text">
          总分({{ reviewData.score }})与各项评分之和({{ dimensionsSum }})不一致
        </span>
      </div>
    </div>

    <!-- 各维度评分 - 动态显示所有维度 -->
    <div v-if="reviewData.dimensions && reviewData.dimensions.length > 0" class="dimensions-section">
      <h4 class="section-title">各项评分</h4>
      <!-- 使用计算属性排序，确保维度按特定顺序显示 -->
      <div class="dimension-item" v-for="(dim, idx) in sortedDimensions" :key="idx">
        <span class="dimension-name">{{ dim.name }}</span>
        <div class="dimension-bar">
          <div class="dimension-fill" :class="getScoreLevel(dim)" :style="{width: getDimensionPercent(dim) + '%'}"></div>
        </div>
        <span class="dimension-score">{{ dim.score }}分</span>
      </div>
    </div>

    <!-- 总体评价 -->
    <div v-if="reviewData.overallComment" class="comment-section">
      <h4 class="section-title">总体评价</h4>
      <p class="overall-comment">{{ reviewData.overallComment }}</p>
    </div>

    <!-- 改进建议 -->
    <div v-if="reviewData.improvements && reviewData.improvements.length > 0" class="improvements-section">
      <h4 class="section-title">改进建议</h4>
      <ul class="improvements-list">
        <li v-for="(item, idx) in reviewData.improvements" :key="idx" class="improvement-item">
          <span class="improvement-number">{{ idx + 1 }}.</span>
          <span class="improvement-content">{{ item }}</span>
        </li>
      </ul>
    </div>

    <!-- 总结 -->
    <div v-if="reviewData.summary" class="summary-section">
      <h4 class="section-title">批改总结</h4>
      <div class="summary-content">
        <div v-if="reviewData.summary.highlights && reviewData.summary.highlights.length > 0" class="summary-item">
          <span class="summary-label">✨ 亮点：</span>
          <span class="summary-text">{{ reviewData.summary.highlights.join('；') }}</span>
        </div>
        <div v-if="reviewData.summary.issues && reviewData.summary.issues.length > 0" class="summary-item">
          <span class="summary-label">⚠️ 问题：</span>
          <span class="summary-text">{{ reviewData.summary.issues.join('；') }}</span>
        </div>
      </div>
    </div>

    <!-- 原始响应 - 已隐藏，不在前端展示 -->
    <!-- 
    <div v-if="reviewData.rawResponse" class="raw-response-section">
      <h4 class="section-title">详细评语</h4>
      <div class="raw-response-content">{{ reviewData.rawResponse }}</div>
    </div>
    -->
  </div>
</template>

<script setup>
/**
 * 作文批改结果展示组件
 * 
 * 负责展示作文批改的完整结果，包括：
 * - 总分和各维度评分（带进度条）
 * - 总体评价
 * - 改进建议
 * - 批改总结（亮点和问题）
 * 
 * 功能特性：
 * - 进度条颜色根据分数动态变化（绿色/黄色/红色）
 * - 支持响应式布局
 * - 清晰的视觉层次
 * - 动态显示所有评分维度（根据作文体裁不同显示不同维度）
 * 
 * @props reviewData - 批改数据对象
 */

import { defineProps, computed } from 'vue';

// 定义组件属性
const props = defineProps({
  reviewData: {
    type: Object,
    default: () => ({
      score: null,
      totalScore: 50,
      essayType: '',
      dimensions: [],
      overallComment: '',
      improvements: [],
      summary: null,
      rawResponse: ''
    })
  }
});

/**
 * 维度满分值映射表
 * 用于计算评分百分比
 * 注意：所有体裁的维度满分之和必须等于50分
 * - 议论文：立意与中心(10) + 论点与论证(18) + 结构与层次(8) + 语言表达(10) + 例证与材料运用(4) = 50
 * - 记叙文：立意与中心(10) + 选材与内容(15) + 结构与层次(8) + 语言表达(10) + 细节与表现(5) + 书写与规范(2) = 50
 * - 说明文：立意与中心(17) + 结构与层次(17) + 语言表达(13) + 方法与技巧(2) + 书写与规范(1) = 50
 */
const maxScores = {
  // 议论文维度
  '立意与中心': 10,
  '论点与论证': 18,
  '结构与层次': 8,
  '语言表达': 10,
  '例证与材料运用': 4,
  // 记叙文维度
  '选材与内容': 15,
  '细节与表现': 5,
  '书写与规范': 2,
  // 说明文维度
  '方法与技巧': 2
};

/**
 * 维度显示优先级映射表
 * 用于确保维度按逻辑顺序显示
 */
const dimensionPriority = {
  '立意与中心': 1,
  '论点与论证': 2,
  '选材与内容': 2,
  '结构与层次': 3,
  '语言表达': 4,
  '例证与材料运用': 5,
  '细节与表现': 5,
  '方法与技巧': 5,
  '书写与规范': 6
};

/**
 * 排序后的维度列表
 * 根据优先级排序，确保显示顺序一致
 */
const sortedDimensions = computed(() => {
  if (!props.reviewData.dimensions || props.reviewData.dimensions.length === 0) {
    return [];
  }
  
  // 复制数组避免修改原数据
  const dims = [...props.reviewData.dimensions];
  
  // 根据优先级排序
  dims.sort((a, b) => {
    const priorityA = dimensionPriority[a.name] || 99;
    const priorityB = dimensionPriority[b.name] || 99;
    return priorityA - priorityB;
  });
  
  return dims;
});

/**
 * 计算各项评分之和
 * 用于与总分进行校验，确保一致性
 */
const dimensionsSum = computed(() => {
  if (!props.reviewData.dimensions || props.reviewData.dimensions.length === 0) {
    return 0;
  }
  return props.reviewData.dimensions.reduce((sum, dim) => sum + (dim.score || 0), 0);
});

/**
 * 总分与各项评分之和的差值
 * 用于检测总分计算是否一致
 */
const scoreDifference = computed(() => {
  if (props.reviewData.score === null || props.reviewData.score === undefined) {
    return 0;
  }
  return props.reviewData.score - dimensionsSum.value;
});

/**
 * 总分是否与各项评分之和一致
 * 允许±1的误差（由于四舍五入可能导致）
 */
const isScoreConsistent = computed(() => {
  return Math.abs(scoreDifference.value) <= 1;
});

/**
 * 计算维度评分进度条百分比
 * 
 * @param {Object} dim - 维度评分对象，包含name和score属性
 * @returns {number} - 进度条百分比（0-100）
 */
const getDimensionPercent = (dim) => {
  // 优先使用维度对象中定义的max_score，否则从映射表查找，默认使用10
  const max = dim.max_score || maxScores[dim.name] || 10;
  const percent = (dim.score / max) * 100;
  return Math.min(percent, 100);
};

/**
 * 获取分数等级，用于动态设置进度条颜色
 * 
 * @param {Object|number} dim - 维度评分对象或百分比数值
 * @returns {string} - 分数等级：'high'、'medium'、'low'
 */
const getScoreLevel = (dim) => {
  let percent;
  
  if (typeof dim === 'object') {
    percent = getDimensionPercent(dim);
  } else if (typeof dim === 'number') {
    percent = dim;
  } else {
    return 'medium';
  }
  
  // 根据百分比返回等级
  if (percent >= 80) {
    return 'high';
  } else if (percent >= 60) {
    return 'medium';
  } else {
    return 'low';
  }
};

/**
 * 获取总分等级，用于动态设置总分圆圈颜色
 * 
 * @param {number} score - 总分
 * @param {number} total - 满分值，默认为50
 * @returns {string} - 分数等级：'high'、'medium'、'low'
 */
const getTotalScoreLevel = (score, total = 50) => {
  const percent = (score / total) * 100;
  if (percent >= 80) {
    return 'high';
  } else if (percent >= 60) {
    return 'medium';
  } else {
    return 'low';
  }
};
</script>

<style scoped>
/**
 * 作文批改结果容器样式
 * 
 * 设计思路：
 * 1. 使用浅灰色背景区分于聊天消息
 * 2. 圆角边框提升视觉舒适度
 * 3. 适当的内边距确保内容不拥挤
 * 
 * 响应式设计：
 * - 默认：padding 20px，margin-top 16px
 * - 平板(<768px)：padding减少到16px
 * - 手机(<480px)：padding减少到12px，圆角减小
 */
.essay-review {
  padding: 20px;
  background-color: #fafafa;
  border-radius: 12px;
  margin-top: 16px;
  /* 确保容器不会溢出 */
  max-width: 100%;
  box-sizing: border-box;
}

/* 标题区域 */
.review-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.review-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.essay-type-badge {
  padding: 4px 12px;
  background-color: #1a73e8;
  color: white;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

/* 总分显示区域 */
.score-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 24px;
}

.score-circle {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  display: flex;
  align-items: baseline;
  justify-content: center;
  transition: background-color 0.3s ease;
}

/* 高分：绿色渐变 */
.score-circle.high {
  background: linear-gradient(135deg, #10b981, #34d399);
}

/* 中分：黄色渐变 */
.score-circle.medium {
  background: linear-gradient(135deg, #f59e0b, #fbbf24);
}

/* 低分：红色渐变 */
.score-circle.low {
  background: linear-gradient(135deg, #ef4444, #f87171);
}

.score-value {
  font-size: 32px;
  font-weight: bold;
  color: white;
}

.score-total {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.score-label {
  margin-top: 8px;
  font-size: 14px;
  color: #666;
}

/* 总分校验警告样式 */
.score-warning {
  margin-top: 8px;
  padding: 6px 12px;
  background-color: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 6px;
  font-size: 12px;
  color: #92400e;
  display: flex;
  align-items: center;
  gap: 6px;
}

.warning-icon {
  font-size: 14px;
}

.warning-text {
  white-space: nowrap;
}

/* 各维度评分区域 */
.dimensions-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e0e0e0;
}

.dimension-item {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.dimension-name {
  width: 100px;
  font-size: 13px;
  color: #555;
  flex-shrink: 0;
}

.dimension-bar {
  flex: 1;
  height: 12px;
  background-color: #f0f0f0;
  border-radius: 6px;
  overflow: hidden;
  margin: 0 12px;
}

.dimension-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.5s ease-out, background-color 0.3s ease;
}

/* 高分进度条：绿色 */
.dimension-fill.high {
  background: linear-gradient(90deg, #10b981, #34d399);
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
}

/* 中分进度条：黄色 */
.dimension-fill.medium {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.4);
}

/* 低分进度条：红色 */
.dimension-fill.low {
  background: linear-gradient(90deg, #ef4444, #f87171);
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.4);
}

.dimension-score {
  font-size: 13px;
  color: #666;
  font-weight: 500;
  min-width: 50px;
  text-align: right;
}

/* 总体评价区域 */
.comment-section {
  margin-bottom: 20px;
}

.overall-comment {
  font-size: 14px;
  line-height: 1.6;
  color: #444;
  white-space: pre-wrap;
}

/* 改进建议区域 */
.improvements-section {
  margin-bottom: 20px;
}

.improvements-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.improvement-item {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  background-color: #fff;
  border-radius: 8px;
  margin-bottom: 8px;
  border-left: 3px solid #1a73e8;
}

.improvement-number {
  font-weight: 600;
  color: #1a73e8;
  flex-shrink: 0;
}

.improvement-content {
  font-size: 14px;
  line-height: 1.5;
  color: #444;
}

/* 总结区域 */
.summary-section {
  margin-bottom: 20px;
}

.summary-content {
  background-color: #fff;
  border-radius: 8px;
  padding: 12px;
}

.summary-item {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.summary-item:last-child {
  margin-bottom: 0;
}

.summary-label {
  font-weight: 600;
  color: #333;
  flex-shrink: 0;
}

.summary-text {
  font-size: 14px;
  color: #444;
  line-height: 1.5;
}

/* 
 * 原始响应区域 - 已隐藏
 * 详细评语内容不在前端展示，减少页面冗余
 * 如需查看原始JSON数据，可在浏览器开发者工具中查看
 */
.raw-response-section {
  display: none; /* 完全隐藏该元素 */
}

/**
 * 响应式设计 - 平板设备 (768px以下)
 */
@media (max-width: 768px) {
  .essay-review {
    padding: 16px;
    margin-top: 12px;
  }
  
  .review-title {
    font-size: 16px;
  }
  
  .score-circle {
    width: 80px;
    height: 80px;
  }
  
  .score-value {
    font-size: 28px;
  }
  
  .dimension-name {
    width: 80px;
    font-size: 12px;
  }
  
  .dimension-score {
    font-size: 12px;
    min-width: 40px;
  }
}

/**
 * 响应式设计 - 手机设备 (480px以下)
 */
@media (max-width: 480px) {
  .essay-review {
    padding: 12px;
    margin-top: 10px;
    border-radius: 10px;
  }
  
  .review-header {
    gap: 8px;
    margin-bottom: 16px;
  }
  
  .review-title {
    font-size: 15px;
  }
  
  .essay-type-badge {
    padding: 3px 10px;
    font-size: 11px;
  }
  
  .score-circle {
    width: 70px;
    height: 70px;
  }
  
  .score-value {
    font-size: 24px;
  }
  
  .score-total {
    font-size: 12px;
  }
  
  .dimension-item {
    margin-bottom: 8px;
  }
  
  .dimension-name {
    width: 70px;
    font-size: 11px;
  }
  
  .dimension-bar {
    height: 10px;
    margin: 0 8px;
  }
  
  .dimension-score {
    font-size: 11px;
    min-width: 35px;
  }
  
  .overall-comment,
  .improvement-content,
  .summary-text {
    font-size: 13px;
  }
}

/**
 * 响应式设计 - 小屏手机 (320px以下)
 */
@media (max-width: 320px) {
  .essay-review {
    padding: 10px;
  }
  
  .dimension-name {
    width: 60px;
    font-size: 10px;
  }
  
  .dimension-score {
    font-size: 10px;
    min-width: 30px;
  }
}

/**
 * 浏览器兼容性处理
 * 所有使用的CSS属性在Chrome 90+、Firefox 88+、Safari 14+、Edge 90+中均支持
 */

/* 打印样式优化 */
@media print {
  .essay-review {
    background-color: #fff;
    border: 1px solid #ddd;
    break-inside: avoid;
  }
}
</style>
