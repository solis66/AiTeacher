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

    <!-- 画布列：舞台（原文+批注+手绘）与底部工具栏 -->
    <div class="stage-col">
      <!-- 主舞台：原文 + 批注叠加 + 手绘层 -->
      <div ref="stageRef" class="stage" @wheel.ctrl.prevent="onWheel">
      <div
        v-if="currentPage"
        ref="innerRef"
        class="stage-inner"
        :style="innerStyle"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerUp"
      >
        <img class="page-img" :src="pageUrl(currentPage.file)" alt="作文原文" draggable="false" />

        <!-- 批注叠加层：坐标全部为相对值，缩放/旋转后仍与原文对齐 -->
        <svg class="ann-layer" :viewBox="`0 0 100 100`" preserveAspectRatio="none">
          <template v-for="ann in pageAnnotations" :key="ann.id">
            <template v-for="(box, bi) in ann.boxes" :key="`${ann.id}-${bi}`">
              <!-- 圈画：圆形/虚线框标记出需要修正的片段 -->
              <rect
                v-if="ann.kind === 'correction'"
                class="ann-shape ann-shape--correction"
                :x="box[0] * 100" :y="box[1] * 100"
                :width="box[2] * 100" :height="box[3] * 100"
                rx="1"
              />
              <!-- 波浪线：问题标注 -->
              <path
                v-else-if="ann.kind === 'issue'"
                class="ann-shape ann-shape--issue"
                :d="wavePath(box)"
              />
              <!-- 实线下划：亮点标注 -->
              <line
                v-else
                class="ann-shape ann-shape--highlight"
                :x1="box[0] * 100" :y1="(box[1] + box[3]) * 100 - 0.3"
                :x2="(box[0] + box[2]) * 100" :y2="(box[1] + box[3]) * 100 - 0.3"
              />
            </template>
          </template>
        </svg>

        <!-- 批注编号 + 纠错文字（DOM 层，便于精确文字排版） -->
        <div class="ann-dom-layer">
          <template v-for="ann in pageAnnotations" :key="`d-${ann.id}`">
            <template v-if="ann.boxes.length">
              <button
                type="button"
                class="ann-badge"
                :class="{ 'is-active': ann.id === activeAnnotation }"
                :style="badgeStyle(ann)"
                :title="ann.suggestion"
                @click.stop="$emit('select-annotation', ann.id)"
              >
                {{ ann.no }}
              </button>
              <!-- 纠错文字：直接叠在原文旁，符合“原文叠加纠错文字”的要求 -->
              <span
                v-if="ann.kind === 'correction' && ann.label"
                class="ann-label"
                :style="labelStyle(ann)"
                @click.stop="$emit('select-annotation', ann.id)"
              >{{ ann.label }}</span>
            </template>
          </template>
        </div>

        <!-- 手工批注层（画笔/形状/文字/橡皮擦） -->
        <canvas ref="drawRef" class="draw-layer" :class="{ 'is-passthrough': tool === 'select' }"></canvas>

        <!-- 文字工具的输入浮层 -->
        <input
          v-if="pendingText"
          ref="textInputRef"
          v-model="pendingText.value"
          class="text-input"
          :style="pendingTextStyle"
          placeholder="输入批注文字，回车确认"
          @keydown.enter.prevent="commitText"
          @keydown.esc.prevent="pendingText = null"
          @blur="commitText"
        />
      </div>

      <div v-else class="stage-empty">该记录暂无可展示的页面</div>
      </div>

      <!-- 底部工具栏：由父组件通过插槽注入，宽度仅占画布区域 -->
      <slot name="toolbar" />
    </div>

    <!-- 批注列表：按编号对应原文位置 -->
    <div class="ann-list">
      <header class="ann-list-head">
        <span>批注（{{ annotations.length }}）</span>
      </header>
      <div class="ann-list-body">
        <div v-if="!annotations.length" class="ann-empty">
          {{ statusHint }}
        </div>
        <button
          v-for="ann in annotations"
          :key="ann.id"
          type="button"
          class="ann-item"
          :class="[{ 'is-active': ann.id === activeAnnotation }, `ann-item--${ann.kind}`]"
          @click="focusAnnotation(ann)"
        >
          <div class="ann-item-head">
            <span class="ann-item-no">{{ ann.no }}</span>
            <span class="ann-item-kind">{{ kindText(ann.kind) }}</span>
            <span v-if="!ann.page" class="ann-item-warn" title="未能在原文中唯一定位，仅展示建议">未定位</span>
          </div>
          <p class="ann-item-quote">{{ ann.quote }}</p>
          <p v-if="ann.suggestion" class="ann-item-sug">{{ ann.suggestion }}</p>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 批改页中栏：原文与批注
 *
 * 需求对应：
 * - 展示图片 / PDF 页面，通过左侧页面缩略图切换
 * - 原文叠加波浪线、圈画、纠错文字及编号
 * - 旁边按编号展示段落亮点、问题分析与修改建议
 * - 点击批注定位对应原文；缩放与旋转后仍保持对齐
 * - 手工批注（画笔/修正符号/形状/文字/橡皮擦）绘制在独立图层
 *
 * 对齐实现要点：
 * - 批注坐标是相对值（0~1），渲染时换算成百分比 / SVG viewBox(0~100)，
 *   因此无论缩放、旋转，叠加层始终跟随原图。
 * - 手绘坐标同样按相对值保存，画布与图片同尺寸，随容器一起变换。
 * - 指针坐标通过逆变换（先反旋转再反缩放）换算，避免受 CSS transform 影响。
 */

import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { reviewPageUrl } from '../../utils/reviewUrl.js';

const props = defineProps({
  record: { type: Object, default: null },
  username: { type: String, default: '' },
  pageIndex: { type: Number, default: 0 },
  zoom: { type: Number, default: 1 },
  rotation: { type: Number, default: 0 },
  tool: { type: String, default: 'select' },
  symbol: { type: String, default: '改' },
  shape: { type: String, default: 'rect' },
  strokeColor: { type: String, default: '#d93025' },
  activeAnnotation: { type: String, default: null }
});

const emit = defineEmits(['update:pageIndex', 'add-mark', 'erase-marks', 'select-annotation', 'commit-marks', 'zoom-delta', 'set-zoom']);

const stageRef = ref(null);
const innerRef = ref(null);
const drawRef = ref(null);
const textInputRef = ref(null);
const pendingText = ref(null);

const pages = computed(() => props.record?.pages || []);
const currentPage = computed(() => pages.value[props.pageIndex] || null);
const marks = computed(() => props.record?.marks || []);

/**
 * 批注：合并 AI 批注与原文纠正，并按阅读顺序编号。
 *
 * 编号顺序（解决“批注顺序错误”）：
 * - AI 返回的 annotations/corrections 数组顺序不可靠，不能直接按数组序编号；
 * - 改为按阅读顺序排序：先页码升序，同页内按批注矩形顶部 y 坐标升序
 *   （y 相同再按 x 升序），未定位（无 page/boxes）的排到最后；
 * - 编号 no 即为排序后的序号，批注列表与图片上的徽标共用同一顺序。
 */
const annotations = computed(() => {
  const result = props.record?.result || {};
  const list = [...(result.annotations || []), ...(result.corrections || [])];
  const sorted = list
    .map((ann, i) => ({ ...ann, _seq: i }))
    .sort((a, b) => {
      const pa = a.page || Infinity;
      const pb = b.page || Infinity;
      if (pa !== pb) return pa - pb;
      const ya = a.boxes?.[0]?.[1] ?? Infinity;
      const yb = b.boxes?.[0]?.[1] ?? Infinity;
      if (ya !== yb) return ya - yb;
      const xa = a.boxes?.[0]?.[0] ?? Infinity;
      const xb = b.boxes?.[0]?.[0] ?? Infinity;
      if (xa !== xb) return xa - xb;
      return a._seq - b._seq;
    });
  return sorted.map((ann, i) => ({ ...ann, no: i + 1 }));
});

const pageAnnotations = computed(() =>
  annotations.value
    .filter((ann) => ann.page === props.pageIndex + 1)
    .map((ann) => ({ ...ann, label: ann.kind === 'correction' ? shortLabel(ann.suggestion) : '' }))
);

/** 批注区为空时的提示：明确区分“没有批注”和“AI 未给出”两种情况 */
const statusHint = computed(() => {
  if (!props.record) return '暂无数据';
  if (props.record.status === 'failed') return '批改失败，暂无批注';
  if (props.record.status !== 'done') return '批改尚未完成';
  return 'AI 未给出批注';
});

// <img> 无法带 X-Username 请求头，必须把 owner 拼进查询参数，否则一律 404
const pageUrl = (file) => reviewPageUrl(props.record?.id, file, props.username);

/** 页面原始尺寸决定舞台尺寸，保证批注坐标与像素一一对应 */
const innerStyle = computed(() => {
  const page = currentPage.value;
  if (!page) return {};
  return {
    width: `${page.width}px`,
    height: `${page.height}px`,
    transform: `scale(${props.zoom}) rotate(${props.rotation}deg)`
  };
});

/** 波浪线路径：把一条矩形区域转成连续的波浪下划线 */
const wavePath = (box) => {
  const x0 = box[0] * 100;
  const y = (box[1] + box[3]) * 100 - 0.4;
  const x1 = (box[0] + box[2]) * 100;
  const step = 1.6;
  const amp = 0.55;
  let d = `M ${x0} ${y}`;
  for (let x = x0; x < x1; x += step) {
    d += ` q ${step / 2} ${-amp} ${step} 0`;
  }
  return d;
};

const badgeStyle = (ann) => {
  const box = ann.boxes[0];
  return {
    left: `${(box[0] + box[2]) * 100}%`,
    top: `${box[1] * 100}%`
  };
};

/** 纠错文字的定位：贴在标注片段右侧，超出右边界时回到片段左侧 */
const labelStyle = (ann) => {
  const box = ann.boxes[0];
  const rightEdge = (box[0] + box[2]) * 100;
  const placeLeft = rightEdge > 62;
  return placeLeft
    ? { right: `${(100 - box[0] * 100)}%`, top: `${(box[1] + box[3]) * 100}%` }
    : { left: `${rightEdge}%`, top: `${(box[1] + box[3]) * 100}%` };
};

const shortLabel = (text) => {
  const clean = String(text || '').replace(/\s+/g, '');
  return clean.length > 14 ? `${clean.slice(0, 14)}…` : clean;
};

const kindText = (kind) => ({ highlight: '亮点', issue: '问题', correction: '纠正' }[kind] || '批注');

// ---------------------------------------------------------------- 画布绘制

/** 把画布像素尺寸与页面像素对齐（按 DPR 提升清晰度） */
const resizeCanvas = () => {
  const page = currentPage.value;
  const canvas = drawRef.value;
  if (!page || !canvas) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = page.width * dpr;
  canvas.height = page.height * dpr;
  canvas.style.width = `${page.width}px`;
  canvas.style.height = `${page.height}px`;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  redraw();
};

/** 重绘所有手工批注（仅当前页） */
const redraw = () => {
  const page = currentPage.value;
  const canvas = drawRef.value;
  if (!page || !canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, page.width, page.height);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  marks.value.filter((m) => m.page === props.pageIndex + 1).forEach((mark) => {
    ctx.strokeStyle = mark.color || props.strokeColor;
    ctx.fillStyle = mark.color || props.strokeColor;

    if (mark.tool === 'pen' && mark.points?.length) {
      ctx.lineWidth = 3;
      ctx.beginPath();
      mark.points.forEach(([x, y], i) => {
        const px = x * page.width;
        const py = y * page.height;
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.stroke();
    } else if (mark.tool === 'shape') {
      ctx.lineWidth = 3;
      const x1 = mark.x1 * page.width;
      const y1 = mark.y1 * page.height;
      const x2 = mark.x2 * page.width;
      const y2 = mark.y2 * page.height;
      if (mark.shape === 'rect') {
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      } else if (mark.shape === 'ellipse') {
        ctx.beginPath();
        ctx.ellipse((x1 + x2) / 2, (y1 + y2) / 2, Math.abs(x2 - x1) / 2, Math.abs(y2 - y1) / 2, 0, 0, Math.PI * 2);
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.moveTo(x1, y2);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    } else if (mark.tool === 'symbol' || mark.tool === 'text') {
      ctx.font = `${mark.size || 26}px "Microsoft YaHei", sans-serif`;
      ctx.textBaseline = 'middle';
      ctx.fillText(mark.text || '', mark.x * page.width, mark.y * page.height);
    }
  });
};

// ------------------------------------------------------------------ 指针交互

const dragging = ref(null);

/**
 * 把客户端坐标换算成页面内的像素坐标。
 * 因为舞台使用了 scale + rotate 的 CSS 变换，必须做一次逆变换才能得到真实位置。
 */
const toPagePoint = (event) => {
  const el = innerRef.value;
  const page = currentPage.value;
  if (!el || !page) return null;
  const rect = el.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const dx = event.clientX - cx;
  const dy = event.clientY - cy;
  const rad = (-props.rotation * Math.PI) / 180;
  const rx = dx * Math.cos(rad) - dy * Math.sin(rad);
  const ry = dx * Math.sin(rad) + dy * Math.cos(rad);
  const x = rx / props.zoom + page.width / 2;
  const y = ry / props.zoom + page.height / 2;
  return { x, y, nx: x / page.width, ny: y / page.height };
};

const onPointerDown = (event) => {
  if (props.tool === 'select') return;
  const point = toPagePoint(event);
  if (!point) return;
  const page = props.pageIndex + 1;

  // 捕获指针：拖出画布范围后仍能持续接收 move/up，避免笔迹中途断掉
  innerRef.value?.setPointerCapture?.(event.pointerId);

  if (props.tool === 'text') {
    // 文字工具：先弹出输入框，回车后再作为一条批注落库
    pendingText.value = { x: point.nx, y: point.ny, value: '' };
    nextTick(() => textInputRef.value?.focus());
    return;
  }

  if (props.tool === 'eraser') {
    eraseAt(point);
    dragging.value = { tool: 'eraser' };
    return;
  }

  if (props.tool === 'symbol') {
    emit('add-mark', {
      tool: 'symbol', text: props.symbol, color: props.strokeColor,
      x: point.nx, y: point.ny, size: 26, page
    });
    return;
  }

  if (props.tool === 'shape') {
    dragging.value = { tool: 'shape', page, start: point, end: point };
    return;
  }

  // 画笔：先落一条起笔记录，后续 move 追加到同一条 mark，避免产生大量碎片
  if (props.tool === 'pen') {
    emit('add-mark', {
      tool: 'pen', color: props.strokeColor, page, points: [[point.nx, point.ny]]
    });
    dragging.value = { tool: 'pen', page, lastIndex: marks.value.length - 1 };
  }
};

const onPointerMove = (event) => {
  if (!dragging.value) return;
  const point = toPagePoint(event);
  if (!point) return;

  if (dragging.value.tool === 'eraser') {
    eraseAt(point);
    return;
  }
  if (dragging.value.tool === 'pen') {
    const mark = marks.value[dragging.value.lastIndex];
    if (mark && mark.tool === 'pen') {
      mark.points.push([point.nx, point.ny]);
      redraw();
    }
    return;
  }
  if (dragging.value.tool === 'shape') {
    dragging.value.end = point;
  }
};

const onPointerUp = (event) => {
  if (!dragging.value) return;
  const state = dragging.value;
  dragging.value = null;
  try { innerRef.value?.releasePointerCapture?.(event?.pointerId); } catch (e) { /* 忽略释放失败 */ }

  if (state.tool === 'pen') {
    // 收尾：只保留有实际长度的笔迹
    const mark = marks.value[state.lastIndex];
    if (mark && mark.points.length < 2) mark.points.push([...mark.points[0]]);
    emit('commit-marks');
  } else if (state.tool === 'shape' && state.start && state.end) {
    // 拖拽距离过小视为误触，不落笔
    const moved = Math.hypot(state.end.nx - state.start.nx, state.end.ny - state.start.ny);
    if (moved > 0.01) {
      emit('add-mark', {
        tool: 'shape', shape: props.shape, color: props.strokeColor, page: state.page,
        x1: state.start.nx, y1: state.start.ny, x2: state.end.nx, y2: state.end.ny
      });
    }
  }
};

/** 橡皮擦：命中即删除整条笔迹，避免残留碎片 */
const eraseAt = (point) => {
  const radius = 14 / props.zoom;
  const page = props.pageIndex + 1;
  const hit = marks.value.filter((mark) => {
    if (mark.page !== page) return false;
    if (mark.tool === 'pen') {
      return mark.points.some(([x, y]) => Math.hypot(x * currentPage.value.width - point.x,
        y * currentPage.value.height - point.y) < radius);
    }
    if (mark.tool === 'symbol' || mark.tool === 'text') {
      return Math.hypot(mark.x * currentPage.value.width - point.x,
        mark.y * currentPage.value.height - point.y) < radius * 2;
    }
    return false;
  });
  if (hit.length) emit('erase-marks', hit.map((m) => m.id));
};

const commitText = () => {
  if (!pendingText.value) return;
  const value = pendingText.value.value.trim();
  if (value) {
    emit('add-mark', {
      tool: 'text', text: value, color: props.strokeColor, size: 22,
      x: pendingText.value.x, y: pendingText.value.y, page: props.pageIndex + 1
    });
  }
  pendingText.value = null;
};

const pendingTextStyle = computed(() => {
  if (!pendingText.value || !currentPage.value) return {};
  return {
    left: `${pendingText.value.x * 100}%`,
    top: `${pendingText.value.y * 100}%`
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

/** 点击批注列表：先切页，再定位到对应位置 */
const focusAnnotation = (ann) => {
  if (ann.page && ann.page !== props.pageIndex + 1) {
    emit('update:pageIndex', ann.page - 1);
  }
  emit('select-annotation', ann.id);
};

// 选中批注后把原文滚动到该位置，完成“点击批注定位原文”
watch(() => props.activeAnnotation, async (id) => {
  if (!id) return;
  await nextTick();
  const ann = pageAnnotations.value.find((a) => a.id === id);
  const stage = stageRef.value;
  const page = currentPage.value;
  if (!ann || !stage || !page || !ann.boxes.length) return;
  const box = ann.boxes[0];
  stage.scrollTo({
    top: Math.max(0, box[1] * page.height * props.zoom - stage.clientHeight / 3),
    left: Math.max(0, box[0] * page.width * props.zoom - stage.clientWidth / 3),
    behavior: 'smooth'
  });
});

// 页面 / 缩放 / 批注变化时重绘手工批注层
watch([() => props.pageIndex, () => props.zoom, () => props.rotation, marks], async () => {
  await nextTick();
  resizeCanvas();
}, { deep: true });

// 记录或页面变化时自动适配：不同记录的页面文件可能同名（都是 page-1.jpg），需同时监听记录 id
watch([() => props.record?.id, () => currentPage.value?.file], async () => {
  await nextTick();
  resizeCanvas();
  fitToStage();
});

onMounted(async () => {
  await nextTick();
  resizeCanvas();
  fitToStage();
});

onBeforeUnmount(() => {
  dragging.value = null;
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
  background: #fff;
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
  background: #fff;
  box-shadow: var(--shadow-2);
}

.page-img { display: block; width: 100%; height: 100%; user-select: none; }

.stage-empty { margin: auto; color: var(--c-text-muted); font-size: var(--fs-md); }

/* 批注叠加 */
.ann-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.ann-shape { fill: none; vector-effect: non-scaling-stroke; }
.ann-shape--correction { stroke: var(--c-error); stroke-width: 2.5; stroke-dasharray: 6 4; }
.ann-shape--issue { stroke: var(--c-error); stroke-width: 2.5; }
.ann-shape--highlight { stroke: var(--c-ok); stroke-width: 3; }

.ann-dom-layer { position: absolute; inset: 0; pointer-events: none; }

.ann-badge {
  position: absolute;
  transform: translate(-50%, -50%);
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  font-size: 13px;
  font-weight: 600;
  line-height: 22px;
  color: #fff;
  background: var(--c-error);
  border: none;
  border-radius: var(--r-pill);
  cursor: pointer;
  pointer-events: auto;
}
.ann-badge.is-active { background: var(--c-primary); box-shadow: 0 0 0 2px rgba(26, 115, 232, .3); }

.ann-label {
  position: absolute;
  max-width: 320px;
  padding: 2px 8px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--c-error);
  background: rgba(252, 232, 230, .97);
  border: 1.5px solid #f5c2be;
  border-radius: 4px;
  cursor: pointer;
  pointer-events: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 手绘层 */
.draw-layer { position: absolute; inset: 0; touch-action: none; }
.draw-layer.is-passthrough { pointer-events: none; }

.text-input {
  position: absolute;
  transform: translate(0, -50%);
  width: 200px;
  padding: 2px 6px;
  font-size: 12px;
  font-family: inherit;
  border: 1px solid var(--c-primary);
  border-radius: 3px;
  outline: none;
  z-index: 5;
}

/* 批注列表 */
.ann-list {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-bg);
  border-left: 1px solid var(--c-border);
  min-height: 0;
}
.ann-list-head {
  padding: 10px 12px;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-secondary);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.ann-list-body { flex: 1; overflow-y: auto; padding: 8px; }
.ann-empty { padding: 20px 8px; text-align: center; font-size: var(--fs-xs); color: var(--c-text-muted); }

.ann-item {
  display: block;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 6px;
  text-align: left;
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-family: inherit;
  transition: border-color .15s, background-color .15s;
}
.ann-item:hover { background: var(--c-bg-subtle); }
.ann-item.is-active { border-color: var(--c-primary); background: var(--c-primary-soft); }
.ann-item--highlight { border-left: 3px solid var(--c-ok); }
.ann-item--issue { border-left: 3px solid var(--c-error); }
.ann-item--correction { border-left: 3px solid var(--c-del); }

.ann-item-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.ann-item-no {
  min-width: 16px;
  height: 16px;
  font-size: 10px;
  line-height: 16px;
  text-align: center;
  color: #fff;
  background: var(--c-error);
  border-radius: var(--r-pill);
}
.ann-item--highlight .ann-item-no { background: var(--c-ok); }
.ann-item-kind { font-size: 11px; color: var(--c-text-secondary); }
.ann-item-warn { font-size: 10px; color: var(--c-del); }

.ann-item-quote {
  margin: 0 0 4px;
  font-size: var(--fs-xs);
  color: var(--c-text);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ann-item-sug { margin: 0; font-size: var(--fs-xs); color: var(--c-text-secondary); line-height: 1.6; }

@media (max-width: 1280px) {
  .ann-list { width: 210px; }
}
@media (max-width: 900px) {
  .ann-list { display: none; }
  .page-strip { width: 52px; }
}
</style>
