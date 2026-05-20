<template>
  <div class="essay-review">
    <!-- 标题区域 -->
    <div class="review-header">
      <span class="review-title">📝 作文批改结果</span>
      <span class="essay-type-badge" :class="essayTypeClass">{{ reviewData.essayType }}</span>
      <span class="essay-type-icon">{{ essayTypeIcon }}</span>
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
        <span class="warning-icon">⚠️</span>
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
      <h4 class="section-title">📌 总体评价</h4>
      <div class="comment-card">
        <p class="overall-comment">{{ reviewData.overallComment }}</p>
      </div>
    </div>

    <!-- 亮点与问题 -->
    <div v-if="hasSummary" class="summary-section">
      <h4 class="section-title">📊 作文分析</h4>
      <div class="summary-grid">
        <!-- 亮点 -->
        <div v-if="reviewData.summary?.highlights?.length > 0" class="summary-card highlights">
          <div class="summary-header">
            <span class="summary-icon">✨</span>
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
            <span class="summary-icon">⚠️</span>
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
      <h4 class="section-title">💡 改进建议</h4>
      <div class="improvements-list">
        <div v-for="(item, idx) in reviewData.improvements" :key="idx" class="improvement-card">
          <div class="improvement-header">
            <span class="improvement-icon">🎯</span>
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
 * 体裁图标映射
 */
const essayTypeIcons = {
  '议论文': '💬',
  '记叙文': '📖',
  '说明文': '📝'
};

/**
 * 获取体裁图标
 */
const essayTypeIcon = computed(() => {
  return essayTypeIcons[props.reviewData.essayType] || '📄';
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
/**
 * 作文批改结果容器样式
 */
.essay-review {
  padding: 24px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 16px;
  margin-top: 20px;
  max-width: 100%;
  box-sizing: border-box;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

/* 标题区域样式 */
.review-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.review-title {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
}

.essay-type-badge {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  color: white;
}

.type-argumentative {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
}

.type-narrative {
  background: linear-gradient(135deg, #f59e0b, #f97316);
}

.type-expository {
  background: linear-gradient(135deg, #10b981, #059669);
}

.essay-type-icon {
  font-size: 24px;
}

/* 总分显示区域样式 */
.score-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 28px;
}

.score-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 40px;
  border-radius: 20px;
  color: white;
  min-width: 160px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
}

.score-card.high {
  background: linear-gradient(135deg, #10b981, #34d399);
}

.score-card.medium {
  background: linear-gradient(135deg, #f59e0b, #fbbf24);
}

.score-card.low {
  background: linear-gradient(135deg, #ef4444, #f87171);
}

.score-main {
  display: flex;
  align-items: baseline;
}

.score-value {
  font-size: 48px;
  font-weight: 800;
}

.score-total {
  font-size: 18px;
  opacity: 0.8;
  margin-left: 4px;
}

.score-label {
  font-size: 14px;
  opacity: 0.9;
  margin-top: 8px;
}

.score-percent {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 4px;
}

/* 总分校验警告样式 */
.score-warning {
  margin-top: 12px;
  padding: 10px 16px;
  background-color: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 10px;
  font-size: 13px;
  color: #92400e;
  display: flex;
  align-items: center;
  gap: 8px;
}

.warning-icon {
  font-size: 16px;
}

/* 维度评分区域样式 */
.dimensions-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.section-subtitle {
  font-size: 13px;
  color: #64748b;
}

/* 维度卡片网格 */
.dimensions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

/* 单个维度卡片 */
.dimension-card {
  background: white;
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: all 0.3s ease;
  border: 2px solid transparent;
}

.dimension-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1);
}

.dimension-card.highlight {
  border-color: rgba(16, 185, 129, 0.3);
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.02) 0%, transparent 100%);
}

/* 维度头部 */
.dimension-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.dimension-name {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.dimension-score-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
}

.dimension-score-badge.high {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.dimension-score-badge.medium {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.dimension-score-badge.low {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

/* 进度条 */
.dimension-progress {
  margin-bottom: 12px;
}

.progress-bar {
  height: 10px;
  background-color: #e2e8f0;
  border-radius: 6px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.6s ease-out;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 8px;
}

.progress-fill.high {
  background: linear-gradient(90deg, #10b981, #34d399);
}

.progress-fill.medium {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
}

.progress-fill.low {
  background: linear-gradient(90deg, #ef4444, #f87171);
}

.progress-text {
  font-size: 10px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
}

/* 维度信息 */
.dimension-info {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.info-label {
  font-size: 11px;
  color: #94a3b8;
}

.info-value {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

/* 评分等级标签 */
.dimension-level {
  display: flex;
  justify-content: flex-end;
}

.level-tag {
  padding: 3px 10px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
}

.level-tag.high {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.level-tag.medium {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.level-tag.low {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

/* 总体评价区域样式 */
.comment-section {
  margin-bottom: 24px;
}

.comment-card {
  background: white;
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.overall-comment {
  font-size: 14px;
  line-height: 1.7;
  color: #475569;
  margin: 0;
  white-space: pre-wrap;
}

/* 总结区域样式 */
.summary-section {
  margin-bottom: 24px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
}

.summary-card {
  background: white;
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.summary-card.highlights {
  border-left: 4px solid #10b981;
}

.summary-card.issues {
  border-left: 4px solid #f59e0b;
}

.summary-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.summary-icon {
  font-size: 18px;
}

.summary-label {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
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
  border-bottom: 1px solid #f1f5f9;
}

.summary-item:last-child {
  border-bottom: none;
}

.item-number {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  flex-shrink: 0;
}

.item-text {
  font-size: 13px;
  line-height: 1.5;
  color: #475569;
}

/* 改进建议区域样式 */
.improvements-section {
  margin-bottom: 24px;
}

.improvements-list {
  display: grid;
  gap: 14px;
}

.improvement-card {
  background: linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 100%);
  border-radius: 14px;
  padding: 18px;
  border: 1px solid rgba(56, 189, 248, 0.2);
}

.improvement-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.improvement-icon {
  font-size: 16px;
}

.improvement-number {
  font-size: 14px;
  font-weight: 600;
  color: #0369a1;
}

.improvement-content {
  font-size: 14px;
  line-height: 1.6;
  color: #334155;
  margin: 0;
}

/**
 * 响应式设计 - 平板设备 (768px以下)
 */
@media (max-width: 768px) {
  .essay-review {
    padding: 18px;
    margin-top: 16px;
  }
  
  .review-title {
    font-size: 18px;
  }
  
  .score-card {
    padding: 20px 32px;
    min-width: 140px;
  }
  
  .score-value {
    font-size: 40px;
  }
  
  .dimensions-grid {
    grid-template-columns: 1fr;
  }
  
  .summary-grid {
    grid-template-columns: 1fr;
  }
}

/**
 * 响应式设计 - 手机设备 (480px以下)
 */
@media (max-width: 480px) {
  .essay-review {
    padding: 14px;
    border-radius: 12px;
  }
  
  .review-header {
    gap: 8px;
    margin-bottom: 20px;
  }
  
  .review-title {
    font-size: 16px;
  }
  
  .essay-type-badge {
    padding: 4px 12px;
    font-size: 12px;
  }
  
  .essay-type-icon {
    font-size: 20px;
  }
  
  .score-card {
    padding: 16px 24px;
    min-width: 120px;
  }
  
  .score-value {
    font-size: 32px;
  }
  
  .score-total {
    font-size: 16px;
  }
  
  .dimension-card {
    padding: 16px;
  }
  
  .dimension-info {
    gap: 12px;
  }
  
  .improvement-card {
    padding: 14px;
  }
}
</style>