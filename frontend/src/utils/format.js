/**
 * 时间格式化工具
 *
 * 此前 ChatHistory.vue 与 ReviewRail.vue 各自维护了一份 formatTime，
 * 格式还不一致（聊天消息只要时分，批改记录要月日+时分），统一收敛到本模块。
 */

/** 两位数补零 */
const pad = (n) => String(n).padStart(2, '0');

/**
 * 格式化聊天消息时间：HH:MM（如 09:05）
 * 用于同一天内的消息展示，无需日期部分
 */
export function formatChatTime(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '';
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * 格式化批改记录时间：MM-DD HH:MM（如 09-16 14:30）
 * 批改记录可能跨天，需要带日期部分
 */
export function formatRecordTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
