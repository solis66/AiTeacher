/**
 * Markdown 渲染工具（AI 回复专用）
 *
 * 背景：
 *   AI 咨询老师的回复本身就是 Markdown 文本（`###` 小标题、`**加粗**`、有序/无序列表、
 *   `> 引用`、表格等），此前用纯文本插值渲染，屏幕上会原样出现 `###`、`**` 这些记号，
 *   既不好读也不像一个"老师"给出的答复。这里统一转成 HTML 后再渲染。
 *
 * 安全（重要）：
 *   回复内容一部分来自模型、一部分来自磁盘上的历史会话文件，都属于**不可信内容**。
 *   直接 v-html 存在 XSS 风险（模型可被诱导输出 <script>、<img onerror=> 之类）。
 *   因此任何 HTML 都必须先过 DOMPurify 白名单净化，不允许出现例外。
 *
 * 性能：
 *   v-for 里放不了 computed，父组件每次重渲染都会重新求值，而 marked 解析是纯函数，
 *   这里按「源文本」做一层容量受限的缓存，避免长回复被反复解析。
 */
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  gfm: true,      // 支持表格、删除线、任务列表
  breaks: true,   // 单个换行也当换行：聊天场景更贴近模型的原始排版意图
});

/*
 * 外链统一新标签打开。
 * DOMPurify 默认会把 target 属性剥掉，所以放在 afterSanitizeAttributes 钩子里补回，
 * 顺序必须是「先净化、后补属性」，否则补上的属性又会被再净化一次。
 */
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && node.getAttribute('href')) {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

/** 缓存条数上限：够覆盖一屏会话，又不至于把长文本一直留在内存里 */
const CACHE_LIMIT = 200;
const cache = new Map();

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * 把 Markdown 文本渲染为可安全插入 DOM 的 HTML 字符串。
 *
 * 参数：
 *   text: string - Markdown 源文本（为空 / 非字符串时返回空串）
 * 返回：
 *   string - 已净化的 HTML；解析异常时退化为纯文本（绝不吞掉整条消息）
 */
export function renderMarkdown(text) {
  const src = typeof text === 'string' ? text : '';
  if (!src.trim()) return '';

  const cached = cache.get(src);
  if (cached !== undefined) return cached;

  let html;
  try {
    html = DOMPurify.sanitize(marked.parse(src));
  } catch (err) {
    console.error('[markdown] 渲染失败，退化为纯文本：', err);
    html = `<p>${escapeHtml(src).replace(/\n/g, '<br>')}</p>`;
  }

  if (cache.size >= CACHE_LIMIT) cache.delete(cache.keys().next().value);
  cache.set(src, html);
  return html;
}
