<template>
  <div class="input-area">
    <!-- 第一行：年级选择（体裁已移除，由 AI 依据题干判定） -->
    <TypeSelector
      v-model:grade="localGrade"
      :disabled="isLoading"
      @update:grade="handleGradeChange"
    />

    <!-- 第二行：命题信息（选填）。与作文正文区分，两项均可单独留空 -->
    <div class="meta-row">
      <label class="meta-field">
        <span class="meta-label">作文题目</span>
        <input
          v-model="localTitle"
          type="text"
          class="ui-input"
          placeholder="选填；仅填题目也可批改"
          :disabled="isLoading"
          maxlength="100"
        />
      </label>
      <label class="meta-field">
        <span class="meta-label">题干要求</span>
        <input
          v-model="localRequirements"
          type="text"
          class="ui-input"
          placeholder="选填；题干若限定体裁将严格按该体裁标准批改，否则按通用标准"
          :disabled="isLoading"
          maxlength="300"
        />
      </label>
    </div>

    <!-- 第三行：作文正文 -->
    <textarea
      ref="textareaRef"
      v-model="inputContent"
      class="ui-textarea body-textarea"
      :placeholder="placeholder"
      :disabled="isLoading"
      @keydown="handleKeyDown"
    ></textarea>

    <!-- 附件预览：展示顺序即提交顺序，支持上移/下移/移除 -->
    <div v-if="attachments.length" class="attachment-strip">
      <div
        v-for="(item, index) in attachments"
        :key="item.uid"
        class="attachment-item"
        :class="{ 'is-first': index === 0 }"
      >
        <div class="attachment-thumb">
          <img v-if="item.kind === 'image'" :src="item.url" :alt="item.name" />
          <div v-else class="attachment-pdf">
            <FileText :size="20" />
            <span>PDF</span>
          </div>
        </div>
        <div class="attachment-meta">
          <span class="attachment-name" :title="item.name">{{ item.name }}</span>
          <span class="attachment-size">{{ formatSize(item.size) }}</span>
        </div>
        <div class="attachment-actions">
          <button
            type="button"
            class="ui-icon-btn"
            data-tip="上移"
            :disabled="index === 0 || isLoading"
            @click="move(index, -1)"
          >
            <ArrowUp :size="14" />
          </button>
          <button
            type="button"
            class="ui-icon-btn"
            data-tip="下移"
            :disabled="index === attachments.length - 1 || isLoading"
            @click="move(index, 1)"
          >
            <ArrowDown :size="14" />
          </button>
          <button
            type="button"
            class="ui-icon-btn"
            data-tip="移除"
            :disabled="isLoading"
            @click="removeAt(index)"
          >
            <X :size="14" />
          </button>
        </div>
        <span v-if="index === 0" class="attachment-order">第1页</span>
      </div>
    </div>

    <!-- 底部操作栏 -->
    <div class="input-footer">
      <div class="input-left">
        <span class="shortcut-hint">Enter 发送 | Shift+Enter 换行</span>
      </div>

      <!-- 需求：「输入栏右侧」放置上传作文图片 / 上传作文 PDF 图标按钮 -->
      <div class="input-right">
        <!-- 上传作文图片（仅 JPG） -->
        <button
          type="button"
          class="ui-icon-btn"
          data-tip="上传作文图片（JPG）"
          :disabled="isLoading"
          @click="pickImages"
        >
          <ImagePlus :size="18" />
        </button>
        <input
          ref="imageInput"
          type="file"
          class="file-input"
          accept=".jpg,image/jpeg"
          multiple
          @change="handleImagePick"
        />

        <!-- 上传作文 PDF -->
        <button
          type="button"
          class="ui-icon-btn"
          data-tip="上传作文 PDF"
          :disabled="isLoading"
          @click="pickPdf"
        >
          <FileText :size="18" />
        </button>
        <input
          ref="pdfInput"
          type="file"
          class="file-input"
          accept=".pdf,application/pdf"
          multiple
          @change="handlePdfPick"
        />

        <span class="char-count">{{ inputContent.length }}/{{ maxLength }}</span>
        <button
          type="button"
          class="ui-btn ui-btn--primary send-btn"
          :disabled="!canSend"
          @click="handleSend"
        >
          <Loader2 v-if="isLoading" :size="14" class="spin" />
          <Send v-else :size="14" />
          <span>{{ isLoading ? '批改中' : '发送' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 首页输入区域组件
 *
 * 本次变更（对应需求「二、首页输入区」）：
 * 1. 保留年级选择（由 TypeSelector 承载），随作文一起提交；作文体裁选择已移除，
 *    由 AI 依据题目与题干要求自动判定体裁并打分。
 * 2. 新增可选的「作文题目」「题干要求」字段，与正文区分；两项都允许留空。
 * 3. 输入栏右侧依次新增「上传作文图片」「上传作文 PDF」图标按钮。
 * 4. 图片仅允许 JPG（前后端双重校验，统一提示「请重新输入jpg格式的图片」）；
 *    PDF 仅接收有效 PDF。
 * 5. 支持多张图片/多页 PDF，提交前展示附件预览、排列顺序与移除操作。
 *
 * @props modelValue 正文内容
 * @props grade      年级
 * @props isLoading  是否正在批改
 * @event send { content, grade, title, requirements, attachments }
 * @event error 需要展示给用户的提示文案
 */

import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { ImagePlus, FileText, Send, X, ArrowUp, ArrowDown, Loader2 } from 'lucide-vue-next';
import TypeSelector from './TypeSelector.vue';

const props = defineProps({
  modelValue: { type: String, default: '' },
  grade: { type: String, default: '' },
  isLoading: { type: Boolean, default: false },
  maxLength: { type: Number, default: 5000 },
  placeholder: { type: String, default: '输入作文正文进行批改，或直接上传作文图片 / PDF…' }
});

const emit = defineEmits(['update:modelValue', 'update:grade', 'send', 'error']);

// 单文件大小上限，与后端 MAX_BYTES 保持一致
const MAX_FILE_BYTES = 20 * 1024 * 1024;
// 一次上传的附件上限：与后端 MAX_PAGES 保持一致。
// 一次上传的全部图片/PDF 属于同一篇作文（合并为一条批改记录），
// 上限为 3 张/页，为后续“批量批改”按作文分组扩展预留。
const MAX_ATTACHMENTS = 3;

const inputContent = ref(props.modelValue);
const localGrade = ref(props.grade);
const localTitle = ref('');
const localRequirements = ref('');
const attachments = ref([]);
const imageInput = ref(null);
const pdfInput = ref(null);
const textareaRef = ref(null);

let uidSeed = 0;

// 同步外部值（会话切换时回填）
watch(() => props.modelValue, (v) => { inputContent.value = v; });
watch(() => props.grade, (v) => { localGrade.value = v; });

/** 是否可发送：正文或附件至少有一项 */
const canSend = computed(() => {
  const hasBody = inputContent.value.trim().length >= 1 && inputContent.value.length <= props.maxLength;
  return (hasBody || attachments.value.length > 0) && !props.isLoading;
});

const handleGradeChange = (grade) => {
  localGrade.value = grade;
  emit('update:grade', grade);
};

const pickImages = () => { if (!props.isLoading) imageInput.value?.click(); };
const pickPdf = () => { if (!props.isLoading) pdfInput.value?.click(); };

/** 格式化文件大小用于展示 */
const formatSize = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

/**
 * 校验并加入图片附件。
 * 需求：只允许 JPG，格式不对统一提示「请重新输入jpg格式的图片」。
 */
const handleImagePick = (event) => {
  const files = Array.from(event.target.files || []);
  for (const file of files) {
    if (attachments.value.length >= MAX_ATTACHMENTS) {
      emit('error', `一次最多上传${MAX_ATTACHMENTS}张图片/PDF（将作为同一篇作文）`);
      break;
    }
    const isJpgName = /\.jpe?g$/i.test(file.name);
    const isJpgType = file.type === 'image/jpeg' || file.type === '';
    if (!isJpgName || !isJpgType || file.size > MAX_FILE_BYTES) {
      // 非 JPG 或超限：统一提示（超限交由后端给出更精确的 20MB 说明）
      emit('error', file.size > MAX_FILE_BYTES ? '单个文件不能超过20MB' : '请重新输入jpg格式的图片');
      continue;
    }
    attachments.value.push({
      uid: `att-${++uidSeed}`,
      file,
      kind: 'image',
      name: file.name,
      size: file.size,
      url: URL.createObjectURL(file)
    });
  }
  event.target.value = '';
};

/** 校验并加入 PDF 附件（仅接收有效 PDF） */
const handlePdfPick = (event) => {
  const files = Array.from(event.target.files || []);
  for (const file of files) {
    if (attachments.value.length >= MAX_ATTACHMENTS) {
      emit('error', `一次最多上传${MAX_ATTACHMENTS}张图片/PDF（将作为同一篇作文）`);
      break;
    }
    const isPdf = /\.pdf$/i.test(file.name) && (file.type === 'application/pdf' || file.type === '');
    if (!isPdf) {
      emit('error', '请上传有效的 PDF 文件');
      continue;
    }
    if (file.size > MAX_FILE_BYTES) {
      emit('error', '单个文件不能超过20MB');
      continue;
    }
    attachments.value.push({
      uid: `att-${++uidSeed}`,
      file,
      kind: 'pdf',
      name: file.name,
      size: file.size,
      url: ''
    });
  }
  event.target.value = '';
};

/** 调整附件顺序（提交顺序即页面顺序） */
const move = (index, delta) => {
  const target = index + delta;
  if (target < 0 || target >= attachments.value.length) return;
  const list = attachments.value;
  [list[index], list[target]] = [list[target], list[index]];
};

/** 移除附件并释放预览地址 */
const removeAt = (index) => {
  const [removed] = attachments.value.splice(index, 1);
  if (removed?.url) URL.revokeObjectURL(removed.url);
};

const handleKeyDown = (event) => {
  if (event.shiftKey && event.key === 'Enter') return;   // 换行
  if (event.key === 'Enter' && !event.isComposing) {
    event.preventDefault();
    handleSend();
  }
};

/** 发送：把年级、题目、题干要求、正文与附件一并交给父组件 */
const handleSend = () => {
  if (!canSend.value) return;
  emit('send', {
    content: inputContent.value,
    grade: localGrade.value,
    title: localTitle.value.trim(),
    requirements: localRequirements.value.trim(),
    attachments: [...attachments.value]
  });
  // 清空输入区（附件交由会话消息持有，返回首页仍可见）
  inputContent.value = '';
  attachments.value.forEach((item) => item.url && URL.revokeObjectURL(item.url));
  attachments.value = [];
};

// 组件销毁时释放所有预览地址，避免内存泄漏
onBeforeUnmount(() => {
  attachments.value.forEach((item) => item.url && URL.revokeObjectURL(item.url));
});
</script>

<style scoped>
.input-area {
  position: relative;
  width: calc(100% - 40px);
  max-width: 900px;
  margin: 10px auto 20px auto;
  padding: 12px 14px;
  background-color: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1);
  flex-shrink: 0;
}

/* 命题信息：两列并排，窄屏自动换行 */
.meta-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 10px 0 8px;
}

.meta-field {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.meta-label {
  flex-shrink: 0;
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
}

.body-textarea {
  min-height: 76px;
  max-height: 200px;
  resize: vertical;
}

/* 附件预览条 */
.attachment-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.attachment-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: var(--c-bg-subtle);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  max-width: 260px;
}

/* 第一个附件即第 1 页，左侧加主色标记 */
.attachment-item.is-first { border-left: 3px solid var(--c-primary); }

.attachment-thumb {
  width: 34px;
  height: 30px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--c-bg-muted);
}

.attachment-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }

.attachment-pdf {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--c-text-secondary);
  font-size: 9px;
  line-height: 1.1;
}

.attachment-meta { display: flex; flex-direction: column; min-width: 0; }
.attachment-name {
  font-size: var(--fs-xs);
  color: var(--c-text);
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attachment-size { font-size: 11px; color: var(--c-text-muted); }

.attachment-actions { display: flex; gap: 0; flex-shrink: 0; }
.attachment-actions .ui-icon-btn { width: 22px; height: 22px; }

.attachment-order {
  position: absolute;
  top: -8px;
  right: -6px;
  padding: 0 5px;
  font-size: 10px;
  color: #fff;
  background: var(--c-primary);
  border-radius: var(--r-pill);
}

/* 底部操作栏 */
.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.input-left { display: flex; align-items: center; gap: 4px; }
.input-right { display: flex; align-items: center; gap: 10px; }

.file-input { display: none; }

.shortcut-hint { font-size: var(--fs-xs); color: var(--c-text-muted); white-space: nowrap; margin-left: 4px; }
.char-count { font-size: var(--fs-xs); color: var(--c-text-muted); white-space: nowrap; }

.send-btn { height: 30px; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 768px) {
  .input-area { width: calc(100% - 24px); padding: 10px; }
  .meta-row { grid-template-columns: 1fr; gap: 8px; }
  .shortcut-hint { display: none; }
}
</style>
