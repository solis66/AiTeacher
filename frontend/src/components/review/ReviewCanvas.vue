<template>
  <div class="canvas-wrap">
    <!-- 页面缩略图：切换多页 -->
    <div class="page-strip">
      <button
        v-for="(p, i) in pages"
        :key="p.file"
        type="button"
        class="page-thumb"
        :class="{ 'is-active': i === pageIndex }"
        :title="`第${i + 1}页`"
        @click="$emit('update:pageIndex', i)"
      >
        <img :src="pageUrl(p.file)" :alt="`第${i + 1}页`" />
        <span class="page-no">{{ i + 1 }}</span>
      </button>
    </div>

    <!-- 画布列：舞台（干净展示原文）与底部工具栏 -->
    <div class="stage-col">
      <!-- 主舞台：原文，支持缩放/旋转 -->
      <div ref="stageRef" class="stage" @wheel.ctrl.prevent="onWheel">
        <div
          v-if="currentPage"
          ref="innerRef"
          class="stage-inner"
          :style="innerStyle"
        >
          <img class="page-img" :src="pageUrl(currentPage.file)" alt="作文原文" draggable="false" />
        </div>

        <div v-else class="stage-empty">该记录暂无可展示的页面</div>
      </div>

      <!-- 底部工具栏：由父组件通过插槽注入，宽度仅占画布区域 -->
      <slot name="toolbar" />
    </div>
  </div>
</template>

<script setup>
/**
 * 批改页中栏：干净展示作文原文
 *
 * 需求对应：
 * - 展示图片 / PDF 页面，通过左侧页面缩略图切换
 * - 支持 Ctrl+滚轮缩放与旋转（对齐保真），原图不被批注图层遮挡
 * - 批注类功能（圈画/编号/手绘/橡皮擦/撤销）已移除，此处仅展示原文
 */

import { ref, computed, watch, nextTick, onMounted } from 'vue';
import { reviewPageUrl } from '../../utils/reviewUrl.js';

const props = defineProps({
  record: { type: Object, default: null },
  username: { type: String, default: '' },
  pageIndex: { type: Number, default: 0 },
  zoom: { type: Number, default: 1 },
  rotation: { type: Number, default: 0 }
});

const emit = defineEmits(['update:pageIndex', 'zoom-delta', 'set-zoom']);

const stageRef = ref(null);
const innerRef = ref(null);

const pages = computed(() => props.record?.pages || []);
const currentPage = computed(() => pages.value[props.pageIndex] || null);

// <img> 无法带 X-Username 请求头，必须把 owner 拼进查询参数，否则一律 404
const pageUrl = (file) => reviewPageUrl(props.record?.id, file, props.username);

/** 页面原始尺寸决定舞台尺寸，保证缩放/旋转后仍以整页为基准 */
const innerStyle = computed(() => {
  const page = currentPage.value;
  if (!page) return {};
  return {
    width: `${page.width}px`,
    height: `${page.height}px`,
    transform: `scale(${props.zoom}) rotate(${props.rotation}deg)`
  };
});

const onWheel = (event) => {
  // Ctrl + 滚轮缩放，与工具栏按钮行为一致
  emit('zoom-delta', event.deltaY < 0 ? 0.1 : -0.1);
};

/** 自动适配：进入批改界面 / 切换页面时，让整页作文完整显示在舞台内 */
const fitToStage = () => {
  const stage = stageRef.value;
  const page = currentPage.value;
  if (!stage || !page || !stage.clientWidth || !stage.clientHeight) return;
  // 与 .stage 的 padding 保持一致，四周留出呼吸空间
  const availW = stage.clientWidth - 40;
  const availH = stage.clientHeight - 40;
  if (availW <= 0 || availH <= 0) return;
  const fit = Number(Math.min(availW / page.width, availH / page.height).toFixed(2));
  if (Math.abs(fit - props.zoom) > 0.005) emit('set-zoom', fit);
  nextTick(centerStage);
};

/** 把缩放后的作文图在舞台内居中：布局盒比舞台大，按视觉中心滚动定位 */
const centerStage = () => {
  const stage = stageRef.value;
  const inner = innerRef.value;
  if (!stage || !inner) return;
  const stageRect = stage.getBoundingClientRect();
  const innerRect = inner.getBoundingClientRect();
  if (!stageRect.width || !stageRect.height) return;
  const visualLeft = innerRect.left - stageRect.left;
  const visualTop = innerRect.top - stageRect.top;
  const deltaLeft = visualLeft + innerRect.width / 2 - stageRect.width / 2;
  const deltaTop = visualTop + innerRect.height / 2 - stageRect.height / 2;
  stage.scrollTo({
    left: Math.max(0, stage.scrollLeft + deltaLeft),
    top: Math.max(0, stage.scrollTop + deltaTop)
  });
};

// 记录或页面变化时自动适配：不同记录的页面文件可能同名（都是 page-1.jpg），需同时监听记录 id
watch(
  [() => props.record?.id, () => currentPage.value?.file],
  async () => {
    await nextTick();
    fitToStage();
  }
);

onMounted(async () => {
  await nextTick();
  fitToStage();
});
</script>

<style scoped>
.canvas-wrap {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
}

/* 页面缩略图条 */
.page-strip {
  width: 62px;
  flex-shrink: 0;
  padding: 8px 6px;
  overflow-y: auto;
  background: var(--c-bg-subtle);
  border-right: 1px solid var(--c-border);
}
.page-thumb {
  position: relative;
  display: block;
  width: 100%;
  margin-bottom: 8px;
  padding: 0;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
}
.page-thumb.is-active { border-color: var(--c-primary); box-shadow: 0 0 0 1px var(--c-primary); }
.page-thumb img { width: 100%; display: block; }
.page-no {
  position: absolute;
  right: 2px;
  bottom: 2px;
  padding: 0 4px;
  font-size: 10px;
  color: #fff;
  background: rgba(32, 33, 36, .6);
  border-radius: 3px;
}

/* 舞台 */
.stage-col {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.stage {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 20px;
  background: var(--c-bg-muted);
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
}

.stage-inner {
  position: relative;
  flex-shrink: 0;
  transform-origin: center center;
  background: var(--c-surface);
  box-shadow: var(--shadow-2);
}

.page-img { display: block; width: 100%; height: 100%; user-select: none; }

.stage-empty { margin: auto; color: var(--c-text-muted); font-size: var(--fs-md); }

@media (max-width: 900px) {
  .page-strip { width: 52px; }
}
</style>