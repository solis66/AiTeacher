/**
 * 批改相关 URL 工具
 *
 * 背景（务必保留本注释）：
 *   批改记录按 X-Username 请求头做归属隔离。但浏览器对 <img src> 发出的请求
 *   无法自定义请求头，后端拿不到 X-Username 就会退化成 anonymous，
 *   于是批改页主图 / 页面缩略图 / 首页入口卡缩略图全部 404。
 *   因此这里把当前用户拼成 owner 查询参数，后端页面图片接口会读它。
 */

/** 拼接页面图片地址，带 owner 参数，供 <img> 直接使用 */
export function reviewPageUrl(reviewId, file, username) {
  if (!reviewId || !file) return '';
  return `/api/review/${reviewId}/page/${file}?owner=${encodeURIComponent(username || 'anonymous')}`;
}

/** 当前登录用户（与请求头 X-Username 保持同一来源：登录时写入的 ai_teacher_user） */
export function currentOwnerName() {
  try {
    return localStorage.getItem('ai_teacher_user') || 'anonymous';
  } catch (e) {
    return 'anonymous';
  }
}
