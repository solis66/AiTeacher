<template>
  <div class="essay-review">
    <!-- 标题区域 -->
    <div class="review-header">
      <span class="review-title">作文批改结果</span>
      <span class="essay-type-badge" :class="essayTypeClass">{{ reviewData.essayType }}</span>
    </div>

    <!-- 总分显示 -->
    <div v-if="reviewData.score !== null && reviewData.score !== undefined" class="score-section">
      <div class="score-card" :class="getTotalScoreLevel(reviewData.score, reviewData.totalScore)">
        <div class="score-main">
          <span class="score-value">{{ reviewData.score }}</span>
          <span class="score-total">/{{ reviewData.totalScore }}</span>
        </div>
        <span class="score-label">总分</span>
        <span class="score-percent">{{ getTotalPercent }}%</span>
      </div>
      <!-- 总分校验警告 -->
      <div v-if="!isScoreConsistent && dimensionsSum > 0" class="score-warning">
        <AlertCircle :size="16" class="warning-icon" />
        <span class="warning-text">
          总分({{ reviewData.score }})与各项评分之和({{ dimensionsSum }})不一致
        </span>
      </div>
    </div>

    <!-- 各维度评分 - 根据体裁动态展示 -->
    <div v-if="sortedDimensions && sortedDimensions.length > 0" class="dimensions-section">
      <div class="section-header">
        <h4 class="section-title">各项评分</h4>
        <span class="section-subtitle">共{{ sortedDimensions.length }}项</span>
      </div>
      
      <!-- 维度卡片列表 -->
      <div class="dimensions-grid">
        <div 
          v-for="(dim, idx) in sortedDimensions" 
          :key="idx"
          class="dimension-card"
          :class="{ 'highlight': dim.score >= dim.max_score * 0.9 }">
          
          <!-- 维度头部 -->
          <div class="dimension-header">
            <span class="dimension-name" :title="dim.name">{{ dim.name }}</span>
            <span class="dimension-score-badge" :class="getScoreLevel(dim)">
              {{ dim.score }}/{{ dim.max_score }}
            </span>
          </div>
          
          <!-- 进度条 -->
          <div class="dimension-progress">
            <div class="progress-bar">
              <div 
                class="progress-fill" 
                :class="getScoreLevel(dim)" 
                :style="{width: getDimensionPercent(dim) + '%'}">
                <span class="progress-text">{{ Math.round(getDimensionPercent(dim)) }}%</span>
              </div>
            </div>
          </div>
          
          <!-- 分数信息 -->
          <div class="dimension-info">
            <span class="info-item">
              <span class="info-label">得分率</span>
              <span class="info-value">{{ getDimensionPercent(dim).toFixed(1) }}%</span>
            </span>
            <span class="info-item">
              <span class="info-label">满分</span>
              <span class="info-value">{{ dim.max_score }}分</span>
            </span>
          </div>
          
          <!-- 评分等级标签 -->
          <div class="dimension-level">
            <span class="level-tag" :class="getScoreLevel(dim)">
              {{ getScoreLevelText(dim) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 总体评价 -->
    <div v-if="reviewData.overallComment" class="comment-section">
      <h4 class="section-title">总体评价</h4>
      <div class="comment-card">
        <p class="overall-comment">{{ reviewData.overallComment }}</p>
      </div>
    </div>

    <!-- 亮点与问题 -->
    <div v-if="hasSummary" class="summary-section">
      <h4 class="section-title">作文分析</h4>
      <div class="summary-grid">
        <!-- 亮点 -->
        <div v-if="reviewData.summary?.highlights?.length > 0" class="summary-card highlights">
          <div class="summary-header">
            <span class="summary-label">亮点</span>
          </div>
          <ul class="summary-list">
            <li v-for="(item, idx) in reviewData.summary.highlights" :key="idx" class="summary-item">
              <span class="item-number">{{ idx + 1 }}</span>
              <span class="item-text">{{ item }}</span>
            </li>
          </ul>
        </div>
        
        <!-- 问题 -->
        <div v-if="reviewData.summary?.issues?.length > 0" class="summary-card issues">
          <div class="summary-header">
            <span class="summary-label">问题</span>
          </div>
          <ul class="summary-list">
            <li v-for="(item, idx) in reviewData.summary.issues" :key="idx" class="summary-item">
              <span class="item-number">{{ idx + 1 }}</span>
              <span class="item-text">{{ item }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 改进建议 -->
    <div v-if="reviewData.improvements && reviewData.improvements.length > 0" class="improvements-section">
      <h4 class="section-title">改进建议</h4>
      <div class="improvements-list">
        <div v-for="(item, idx) in reviewData.improvements" :key="idx" class="improvement-card">
          <div class="improvement-header">
            <span class="improvement-number">建议{{ idx + 1 }}</span>
          </div>
          <p class="improvement-content">{{ item }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 作文批改结果展示组件
 * 
 * 功能说明：
 * 本组件负责展示作文批改的完整结果，包括总分、各维度评分、总体评价和改进建议。
 * 核心特性是根据作文体裁动态展示对应的评分维度，确保符合各体裁专业评分标准。
 * 
 * 支持的作文体裁：
 * - 记叙文：6项评分维度（立意与中心、选材与内容、结构与层次、语言表达、细节与表现、书写与规范）
 * - 说明文：5项评分维度（立意与中心、结构与层次、语言表达、方法与技巧、书写与规范）
 * - 议论文：5项评分维度（立意与中心、论点与论证、结构与层次、语言表达、例证与材料运用）
 * 
 * 实现思路：
 * 1. 定义体裁-维度映射表，明确各体裁应展示的评分维度
 * 2. 使用计算属性根据体裁动态筛选和排序维度
 * 3. 通过CSS Grid实现响应式卡片布局
 * 4. 添加性能优化，避免不必要的重渲染
 * 
 * @props reviewData - 批改数据对象
 */

import { defineProps, computed } from 'vue';
import { AlertCircle } from 'lucide-vue-next';

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
 * 获取体裁样式类
 */
const essayTypeClass = computed(() => {
  const typeClasses = {
    '议论文': 'type-argumentative',
    '记叙文': 'type-narrative',
    '说明文': 'type-expository'
  };
  return typeClasses[props.reviewData.essayType] || '';
});

/**
 * 体裁-维度映射配置表
 * 
 * 设计说明：
 * 该配置表定义了不同作文体裁对应的评分维度列表，确保：
 * 1. 各体裁只展示其专业的评分维度
 * 2. 维度顺序符合评分逻辑（从内容到形式）
 * 3. 便于后续维护和扩展新的体裁
 * 
 * 数据结构：
 * - key: 体裁名称（与后端返回的essayType保持一致）
 * - value: 维度名称数组，按显示顺序排列
 */
const essayTypeDimensionsMap = {
  '记叙文': [
    '立意与中心',
    '选材与内容', 
    '结构与层次',
    '语言表达',
    '细节与表现',
    '书写与规范'
  ],
  '说明文': [
    '立意与中心',
    '结构与层次',
    '语言表达',
    '方法与技巧',
    '书写与规范'
  ],
  '议论文': [
    '立意与中心',
    '论点与论证',
    '结构与层次',
    '语言表达',
    '例证与材料运用'
  ]
};

/**
 * 体裁-维度满分值映射表
 * 
 * 设计说明：
 * 采用嵌套字典结构，外层键为体裁名称，内层键为维度名称，值为该维度的满分值。
 * 这样可以避免不同体裁共享维度名称导致的值覆盖问题。
 * 
 * 满分配置（各体裁维度满分之和均为50分）：
 * - 议论文：立意与中心(10) + 论点与论证(18) + 结构与层次(8) + 语言表达(10) + 例证与材料运用(4) = 50
 * - 记叙文：立意与中心(10) + 选材与内容(15) + 结构与层次(8) + 语言表达(10) + 细节与表现(5) + 书写与规范(2) = 50
 * - 说明文：立意与中心(17) + 结构与层次(17) + 语言表达(13) + 方法与技巧(2) + 书写与规范(1) = 50
 */
const dimensionMaxScores = {
  '议论文': {
    '立意与中心': 10,
    '论点与论证': 18,
    '结构与层次': 8,
    '语言表达': 10,
    '例证与材料运用': 4
  },
  '记叙文': {
    '立意与中心': 10,
    '选材与内容': 15,
    '结构与层次': 8,
    '语言表达': 10,
    '细节与表现': 5,
    '书写与规范': 2
  },
  '说明文': {
    '立意与中心': 17,
    '结构与层次': 17,
    '语言表达': 13,
    '方法与技巧': 2,
    '书写与规范': 1
  }
};

/**
 * 获取当前体裁对应的维度配置
 * 
 * 功能说明：
 * 根据reviewData中的essayType获取对应的维度列表。
 * 如果体裁未定义或不存在，返回空数组。
 * 
 * @returns {Array} - 当前体裁的维度名称数组
 */
const currentTypeDimensions = computed(() => {
  const essayType = props.reviewData.essayType || '';
  return essayTypeDimensionsMap[essayType] || [];
});

/**
 * 排序后的维度列表（核心计算属性）
 * 
 * 功能说明：
 * 这是本组件的核心计算属性，负责：
 * 1. 根据作文体裁筛选应显示的维度
 * 2. 按照体裁配置的顺序对维度进行排序
 * 3. 过滤掉不属于当前体裁的维度
 * 4. 补充各维度的满分值（从配置表中获取）
 * 
 * 实现思路：
 * 1. 获取当前体裁的维度配置列表（currentTypeDimensions）
 * 2. 创建维度名称到数据对象的映射，便于快速查找
 * 3. 遍历配置列表，按顺序从映射中查找对应维度数据
 * 4. 如果维度数据存在，补充满分值后加入结果数组
 * 5. 返回按体裁配置顺序排列的完整维度数组
 * 
 * @returns {Array} - 按体裁配置排序后的维度数组
 */
const sortedDimensions = computed(() => {
  const dimensions = props.reviewData.dimensions || [];
  
  if (dimensions.length === 0) {
    return [];
  }
  
  const essayType = props.reviewData.essayType || '';
  const typeDimensions = currentTypeDimensions.value;
  
  if (typeDimensions.length === 0) {
    console.warn('[EssayReview] 未知的作文体裁:', essayType);
    return dimensions;
  }
  
  const dimensionMap = new Map();
  dimensions.forEach(dim => {
    if (dim && dim.name) {
      dimensionMap.set(dim.name, dim);
    }
  });
  
  const typeMaxScores = dimensionMaxScores[essayType] || {};
  
  const sortedResult = [];
  typeDimensions.forEach(dimName => {
    const dimData = dimensionMap.get(dimName);
    if (dimData) {
      const maxScore = dimData.max_score || typeMaxScores[dimName] || 10;
      sortedResult.push({
        ...dimData,
        max_score: maxScore
      });
    }
  });
  
  return sortedResult;
});

/**
 * 计算各项评分之和
 * 
 * @returns {number} - 各项评分之和
 */
const dimensionsSum = computed(() => {
  const dims = sortedDimensions.value;
  if (dims.length === 0) {
    return 0;
  }
  return dims.reduce((sum, dim) => sum + (dim.score || 0), 0);
});

/**
 * 总分百分比
 * 
 * @returns {number} - 总分百分比
 */
const getTotalPercent = computed(() => {
  if (props.reviewData.score === null || props.reviewData.score === undefined) {
    return 0;
  }
  return ((props.reviewData.score / props.reviewData.totalScore) * 100).toFixed(1);
});

/**
 * 总分与各项评分之和是否一致
 * 
 * @returns {boolean} - 是否一致
 */
const isScoreConsistent = computed(() => {
  if (props.reviewData.score === null || props.reviewData.score === undefined) {
    return true;
  }
  return Math.abs(props.reviewData.score - dimensionsSum.value) <= 1;
});

/**
 * 是否有总结内容
 */
const hasSummary = computed(() => {
  const summary = props.reviewData.summary;
  return summary && (summary.highlights?.length > 0 || summary.issues?.length > 0);
});

/**
 * 计算维度评分进度条百分比
 * 
 * @param {Object} dim - 维度评分对象
 * @returns {number} - 进度条百分比（0-100）
 */
const getDimensionPercent = (dim) => {
  if (!dim || typeof dim.score !== 'number' || typeof dim.max_score !== 'number') {
    return 0;
  }
  
  if (dim.max_score <= 0) {
    return 0;
  }
  
  const percent = (dim.score / dim.max_score) * 100;
  return Math.min(Math.max(percent, 0), 100);
};

/**
 * 获取分数等级，用于动态设置样式
 * 
 * @param {Object|number} dim - 维度评分对象或百分比数值
 * @returns {string} - 分数等级：'high'、'medium'、'low'
 */
const getScoreLevel = (dim) => {
  let percent;
  
  if (typeof dim === 'object' && dim !== null) {
    percent = getDimensionPercent(dim);
  } else if (typeof dim === 'number') {
    percent = dim;
  } else {
    return 'medium';
  }
  
  if (percent >= 80) {
    return 'high';
  } else if (percent >= 60) {
    return 'medium';
  } else {
    return 'low';
  }
};

/**
 * 获取分数等级文本描述
 * 
 * @param {Object} dim - 维度评分对象
 * @returns {string} - 等级描述
 */
const getScoreLevelText = (dim) => {
  const level = getScoreLevel(dim);
  const levelTexts = {
    'high': '优秀',
    'medium': '良好',
    'low': '需改进'
  };
  return levelTexts[level] || '良好';
};

/**
 * 获取总分等级
 * 
 * @param {number} score - 总分
 * @param {number} total - 满分值
 * @returns {string} - 分数等级
 */
const getTotalScoreLevel = (score, total = 50) => {
  if (typeof score !== 'number' || typeof total !== 'number' || total === 0) {
    return 'medium';
  }
  
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
.essay-review {
  padding: 20px;
  background: var(--c-bg);
  max-width: 100%;
  box-sizing: border-box;
}

/* 标题区域 */
.review-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.review-title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--c-text);
}

.essay-type-badge {
  padding: 3px 10px;
  border-radius: var(--r-pill);
  font-size: var(--fs-xs);
  font-weight: 600;
}

.type-argumentative { color: var(--c-primary); background: var(--c-primary-soft); }
.type-narrative     { color: var(--c-ok); background: var(--c-ok-soft); }
.type-expository    { color: var(--c-warn); background: var(--c-warn-soft); }

/* 总分显示 */
.score-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 24px;
}

.score-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px 32px;
  border-radius: var(--r-lg);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  min-width: 140px;
}

.score-card.high   { border-left: 4px solid var(--c-ok); }
.score-card.medium { border-left: 4px solid var(--c-warn); }
.score-card.low    { border-left: 4px solid var(--c-error); }

.score-main {
  display: flex;
  align-items: baseline;
}

.score-value {
  font-size: 40px;
  font-weight: 800;
  color: var(--c-text);
}

.score-total {
  font-size: var(--fs-md);
  color: var(--c-text-secondary);
  margin-left: 4px;
}

.score-label {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  margin-top: 6px;
}

.score-percent {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  margin-top: 2px;
}

/* 总分校验警告 */
.score-warning {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--c-warn-soft);
  border: 1px solid rgba(154, 103, 0, 0.14);
  border-radius: var(--r-md);
  font-size: var(--fs-sm);
  color: var(--c-warn);
  display: flex;
  align-items: center;
  gap: 6px;
}

.warning-icon {
  display: inline-flex;
  flex-shrink: 0;
}

/* 维度评分 */
.dimensions-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.section-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--c-text);
  margin: 0;
}

.section-subtitle {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
}

.dimensions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.dimension-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: 16px;
}

.dimension-card.highlight {
  border-color: var(--c-ok);
  background: var(--c-ok-soft);
}

.dimension-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.dimension-name {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-text);
}

.dimension-score-badge {
  padding: 2px 8px;
  border-radius: var(--r-pill);
  font-size: var(--fs-sm);
  font-weight: 700;
}

.dimension-score-badge.high,
.progress-fill.high,
.level-tag.high {
  color: var(--c-ok);
  background: var(--c-ok-soft);
}

.dimension-score-badge.medium,
.progress-fill.medium,
.level-tag.medium {
  color: var(--c-warn);
  background: var(--c-warn-soft);
}

.dimension-score-badge.low,
.progress-fill.low,
.level-tag.low {
  color: var(--c-error);
  background: var(--c-error-soft);
}

.dimension-progress {
  margin-bottom: 10px;
}

.progress-bar {
  height: 8px;
  background: var(--c-bg-muted);
  border-radius: var(--r-pill);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: var(--r-pill);
  transition: width 0.4s ease-out;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 6px;
}

.progress-text {
  font-size: 10px;
  font-weight: 700;
  color: inherit;
}

.dimension-info {
  display: flex;
  gap: 14px;
  margin-bottom: 10px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.info-label {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

.info-value {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--c-text);
}

.dimension-level {
  display: flex;
  justify-content: flex-end;
}

.level-tag {
  padding: 2px 8px;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: 700;
}

/* 总体评价 */
.comment-section {
  margin-bottom: 24px;
}

.comment-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: 16px;
}

.overall-comment {
  font-size: var(--fs-md);
  line-height: 1.7;
  color: var(--c-text);
  margin: 0;
  white-space: pre-wrap;
}

/* 作文分析 */
.summary-section {
  margin-bottom: 24px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.summary-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: 16px;
}

.summary-card.highlights {
  border-left: 3px solid var(--c-ok);
}

.summary-card.issues {
  border-left: 3px solid var(--c-warn);
}

.summary-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.summary-label {
  font-size: var(--fs-md);
  font-weight: 700;
  color: var(--c-text);
}

.summary-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.summary-item {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--c-border);
}

.summary-item:last-child {
  border-bottom: none;
}

.item-number {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--c-bg-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--c-text-secondary);
  flex-shrink: 0;
}

.item-text {
  font-size: var(--fs-sm);
  line-height: 1.6;
  color: var(--c-text);
}

/* 改进建议 */
.improvements-section {
  margin-bottom: 24px;
}

.improvements-list {
  display: grid;
  gap: 12px;
}

.improvement-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-left: 3px solid var(--c-primary);
  border-radius: var(--r-lg);
  padding: 14px 16px;
}

.improvement-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.improvement-number {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--c-primary);
}

.improvement-content {
  font-size: var(--fs-md);
  line-height: 1.7;
  color: var(--c-text);
  margin: 0;
}

@media (max-width: 768px) {
  .essay-review { padding: 16px; }
  .score-value { font-size: 34px; }
  .dimensions-grid { grid-template-columns: 1fr; }
  .summary-grid { grid-template-columns: 1fr; }
}

@media (max-width: 480px) {
  .essay-review { padding: 14px; }
  .review-title { font-size: var(--fs-lg); }
  .score-card { padding: 16px 24px; min-width: 120px; }
  .score-value { font-size: 30px; }
}
</style>