<template>
  <section class="submit-page">
    <header class="page-head">
      <h2 class="page-title">开始批改</h2>
      <p class="page-sub">提交作文正文或上传图片/PDF，AI 依据题目要求进行批改</p>
    </header>

    <div class="mode-switch">
      <button
        type="button"
        class="mode-btn"
        :class="{ 'is-active': mode === 'single' }"
        @click="mode = 'single'"
      >单次批改（最多3张图）</button>
      <button
        type="button"
        class="mode-btn"
        :class="{ 'is-active': mode === 'batch' }"
        @click="mode = 'batch'"
      >批量批改（最多2篇/6张图）</button>
    </div>

    <div class="essay-list">
      <article
        v-for="(essay, index) in essays"
        :key="essay.key"
        class="essay-card"
      >
        <h3 class="essay-title">
          作文 {{ index + 1 }}
          <span v-if="mode === 'batch'" class="essay-hint">每篇最多3张图片/PDF</span>
        </h3>

        <div class="form-row">
          <label class="field">
            <span class="field-label">年级 <em>*</em></span>
            <select v-model="essay.grade" class="ui-input">
              <option value="" disabled>请选择年级</option>
              <option v-for="g in grades" :key="g" :value="g">{{ g }}</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">体裁（可选）</span>
            <select v-model="essay.essayType" class="ui-input">
              <option value="">由AI依题干判定</option>
              <option v-for="t in essayTypes" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">学生归属（可选）</span>
            <input v-model="essay.student" class="ui-input" placeholder="留空=提交者本人" />
          </label>
        </div>

        <label class="field">
          <span class="field-label field-label--ocr">
            <span>作文题目（可选）</span>
            <button
              type="button"
              class="ocr-btn"
              :disabled="!!ocrBusy[`${index}-title`]"
              @click.prevent.stop="pickOcr(index, 'title')"
            >
              <Loader2 v-if="ocrBusy[`${index}-title`]" :size="12" class="spin" />
              <ImagePlus v-else :size="12" />
              <span>{{ ocrBusy[`${index}-title`] ? '识别中…' : '图片识别' }}</span>
            </button>
          </span>
          <input v-model="essay.title" class="ui-input" placeholder="例如：那一刻，我长大了" />
        </label>

        <label class="field">
          <span class="field-label field-label--ocr">
            <span>题干要求（可选）</span>
            <button
              type="button"
              class="ocr-btn"
              :disabled="!!ocrBusy[`${index}-requirements`]"
              @click.prevent.stop="pickOcr(index, 'requirements')"
            >
              <Loader2 v-if="ocrBusy[`${index}-requirements`]" :size="12" class="spin" />
              <ImagePlus v-else :size="12" />
              <span>{{ ocrBusy[`${index}-requirements`] ? '识别中…' : '图片识别' }}</span>
            </button>
          </span>
          <textarea v-model="essay.requirements" class="ui-textarea" rows="2" placeholder="例如：不少于500字，结合自身经历"></textarea>
        </label>

        <!-- 题目/题干识图共用一个隐藏选择器，选中后由 ocrTarget 决定回填到哪个字段 -->
        <input
          ref="ocrInput"
          type="file"
          accept="image/jpeg"
          class="visually-hidden"
          @change="onOcrPick"
        />

        <label class="field">
          <span class="field-label">作文正文</span>
          <textarea v-model="essay.body" class="ui-textarea body-box" placeholder="在此输入作文正文，或上传作文图片/PDF"></textarea>
        </label>

        <div class="upload-row field">
          <button
            type="button"
            class="ui-btn ui-btn--ghost"
            @click="pickFiles(index)"
          >
            <Upload :size="14" /><span>上传图片 / PDF</span>
          </button>
          <span class="upload-count">{{ essay.files.length }} / 3</span>
          <input
            ref="fileInputs"
            type="file"
            accept="image/jpeg,image/png,image/webp,.pdf"
            multiple
            class="visually-hidden"
            @change="onFiles(index, $event)"
          />
          <span v-if="essay.files.length" class="file-list">
            <span v-for="(f, fi) in essay.files" :key="fi" class="file-chip">
              {{ f.name }}
              <button type="button" class="file-remove" @click="removeFile(index, fi)">×</button>
            </span>
          </span>
        </div>

        <button
          v-if="mode === 'batch' && essays.length > 1"
          type="button"
          class="ui-text-btn danger"
          @click="removeEssay(index)"
        >移除本篇</button>
      </article>
    </div>

    <button
      v-if="mode === 'batch' && essays.length < 2"
      type="button"
      class="ui-btn ui-btn--ghost add-essay"
      @click="addEssay"
    ><Plus :size="14" /><span>再添加一篇作文</span></button>

    <footer class="submit-footer">
      <p v-if="error" class="submit-error">{{ error }}</p>
      <button
        type="button"
        class="ui-btn ui-btn--primary submit-btn"
        :disabled="submitting"
        @click="submit"
      >
        <Loader2 v-if="submitting" :size="14" class="spin" />
        <Sparkles v-else :size="14" />
        <span>{{ submitting ? '提交批改中…' : '开始批改' }}</span>
      </button>
    </footer>
  </section>
</template>

<script setup>
/**
 * 开始批改（需求 4.1）
 * - 单次批改：1 篇，图片/PDF 最多 3 张
 * - 批量批改：最多 2 篇、单次最多 6 张（每篇 ≤3），后端拆成多条独立记录聚合
 */
import { ref, reactive } from 'vue';
import { Upload, Plus, Loader2, Sparkles, ImagePlus } from 'lucide-vue-next';
import request from '../../api/request.js';

const props = defineProps({ username: { type: String, default: '' } });
const emit = defineEmits(['submitted', 'error']);

const grades = ['七年级', '八年级', '九年级'];
const essayTypes = ['议论文', '记叙文', '说明文'];
const MAX_FILES_PER_ESSAY = 3;
const MAX_ESSAYS = 2;

const mode = ref('single');
const submitting = ref(false);
const error = ref('');
const fileInputs = ref([]);

// 题目 / 题干要求的「图片识别」：共用一个隐藏 input，由 ocrTarget 决定回填到哪个字段。
// ocrBusy 的 key 形如 `0-title`，用来逐个字段显示「识别中…」，互不干扰。
const ocrInput = ref(null);
const ocrTarget = ref(null);
const ocrBusy = reactive({});

const essayTemplate = () => ({
  key: Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
  grade: '', essayType: '', student: '', title: '', requirements: '', body: '', files: []
});
const essays = reactive([essayTemplate()]);

const addEssay = () => {
  if (essays.length >= MAX_ESSAYS) return;
  essays.push(essayTemplate());
};
const removeEssay = (index) => { if (essays.length > 1) essays.splice(index, 1); };

const ownerHeader = () => ({ 'X-Username': props.username || 'anonymous' });

const pickFiles = (index) => { const el = fileInputs.value[index]; if (el) el.click(); };

const onFiles = (index, event) => {
  const essay = essays[index];
  const chosen = Array.from(event.target.files || []);
  const remain = MAX_FILES_PER_ESSAY - essay.files.length;
  const added = chosen.slice(0, remain);
  added.forEach((f) => essay.files.push(f));
  if (chosen.length > remain) error.value = `每篇最多上传${MAX_FILES_PER_ESSAY}张，多余文件已忽略`;
  event.target.value = '';
};
const removeFile = (index, fi) => { essays[index].files.splice(fi, 1); };

/** 打开识图选择器，并记下这次结果该回填到哪个字段 */
const pickOcr = (index, field) => {
  ocrTarget.value = { index, field };
  const el = ocrInput.value;
  if (el) el.click();
};

const onOcrPick = async (event) => {
  const file = (event.target.files || [])[0];
  event.target.value = '';            // 清空以便重复选择同一张图片
  const target = ocrTarget.value;
  if (!file || !target) return;

  const { index, field } = target;
  const key = `${index}-${field}`;
  ocrBusy[key] = true;
  try {
    const fd = new FormData();
    fd.append('image', file, file.name);
    const res = await request.post('/ocr', fd, { headers: ownerHeader() });
    if (!res.data.success) throw new Error(res.data.message || '图片识别失败');
    const text = (res.data.data?.text || '').trim();
    if (!text) throw new Error('未能识别出文字，请换一张更清晰的图片');
    const essay = essays[index];
    if (!essay) return;
    // 题目是单行输入，把识别结果里的换行压平；题干是文本域，保留原有换行
    if (field === 'title') essay.title = text.replace(/\s*\n+\s*/g, ' ').trim();
    else essay.requirements = text;
  } catch (e) {
    error.value = e.response?.data?.message || e.message || '图片识别失败';
  } finally {
    ocrBusy[key] = false;
    ocrTarget.value = null;
  }
};

const validate = () => {
  if (essays.some((e) => !e.grade)) { error.value = '请为每篇作文选择年级'; return false; }
  if (essays.some((e) => !e.body.trim() && e.files.length === 0)) {
    error.value = '每篇作文需填写正文，或上传图片/PDF'; return false;
  }
  if (essays.some((e) => e.files.length > MAX_FILES_PER_ESSAY)) {
    error.value = `每篇最多上传${MAX_FILES_PER_ESSAY}张图片/PDF`; return false;
  }
  const totalFiles = essays.reduce((n, e) => n + e.files.length, 0);
  if (mode.value === 'batch' && totalFiles > 6) { error.value = '批量批改单次最多上传6张图片/PDF'; return false; }
  return true;
};

const submit = async () => {
  error.value = '';
  if (submitting.value || !validate()) return;
  submitting.value = true;
  try {
    if (mode.value === 'single') {
      const fd = new FormData();
      const e = essays[0];
      fd.append('grade', e.grade);
      fd.append('essay_type', e.essayType);
      fd.append('title', e.title);
      fd.append('requirements', e.requirements);
      fd.append('body', e.body);
      fd.append('student', e.student);
      e.files.forEach((file) => fd.append('files', file, file.name));
      const res = await request.post('/api/review', fd, { headers: ownerHeader() });
      if (!res.data.success) throw new Error(res.data.message || '提交失败');
      emit('submitted', [res.data.data]);
    } else {
      const fd = new FormData();
      fd.append('essay_count', String(essays.length));
      essays.forEach((e, i) => {
        fd.append(`grade_${i}`, e.grade);
        fd.append(`essay_type_${i}`, e.essayType);
        fd.append(`title_${i}`, e.title);
        fd.append(`requirements_${i}`, e.requirements);
        fd.append(`body_${i}`, e.body);
        fd.append(`student_${i}`, e.student);
        e.files.forEach((file) => fd.append(`files_${i}`, file, file.name));
      });
      const res = await request.post('/api/review/batch', fd, { headers: ownerHeader() });
      if (!res.data.success) throw new Error(res.data.message || '提交失败');
      emit('submitted', res.data.data || []);
    }
    resetForm();
  } catch (e) {
    error.value = e.response?.data?.message || e.message || '提交失败';
    emit('error', error.value);
  } finally {
    submitting.value = false;
  }
};

const resetForm = () => { essays.splice(0, essays.length, essayTemplate()); };
</script>

<style scoped>
.submit-page { max-width: 860px; margin: 0 auto; padding: 24px 28px 48px; overflow-y: auto; height: 100%; }
.page-head { margin-bottom: 16px; }
.page-title { font-size: var(--fs-xl); font-weight: 700; color: var(--c-text); margin-bottom: 4px; }
.page-sub { font-size: var(--fs-sm); color: var(--c-text-secondary); margin: 0; }

.mode-switch { display: inline-flex; gap: 0; padding: 3px; background: var(--c-bg-muted); border-radius: var(--r-lg); margin-bottom: 20px; }
.mode-btn { padding: 7px 16px; font-family: inherit; font-size: var(--fs-sm); border: none; border-radius: var(--r-md); background: transparent; color: var(--c-text-secondary); cursor: pointer; }
.mode-btn.is-active { background: var(--c-surface); color: var(--c-text); font-weight: 600; box-shadow: var(--shadow-1); }

.essay-card { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); padding: 20px; margin-bottom: 16px; }
.essay-title { display: flex; align-items: center; gap: 8px; font-size: var(--fs-md); font-weight: 600; margin: 0 0 14px; }
.essay-hint { font-size: 12px; font-weight: 400; color: var(--c-text-muted); }

.form-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }
.field-label { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.field-label em { color: var(--c-error); font-style: normal; }
.field-label--ocr { display: flex; align-items: center; gap: 8px; }
.ocr-btn { display: inline-flex; align-items: center; gap: 3px; padding: 2px 8px; font-family: inherit; font-size: 11px; color: var(--c-primary); background: var(--c-primary-soft); border: none; border-radius: var(--r-pill); cursor: pointer; }
.ocr-btn:disabled { opacity: .6; cursor: default; }
.body-box { min-height: 140px; line-height: 1.8; }

.upload-row { flex-direction: row; align-items: center; gap: 10px; flex-wrap: wrap; }
.upload-count { font-size: var(--fs-xs); color: var(--c-text-muted); }
.file-list { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.file-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; font-size: 12px; background: var(--c-bg-muted); border-radius: var(--r-pill); }
.file-remove { border: none; background: none; cursor: pointer; color: var(--c-text-muted); font-size: 14px; line-height: 1; }
.visually-hidden { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }

.add-essay { margin-bottom: 16px; }
.ui-text-btn.danger { margin-top: 4px; color: var(--c-error); }

.submit-footer { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding-top: 12px; border-top: 1px solid var(--c-border); }
.submit-error { font-size: var(--fs-sm); color: var(--c-error); margin: 0; }
.submit-btn { min-width: 160px; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>