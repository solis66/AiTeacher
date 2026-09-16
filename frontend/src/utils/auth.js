/**
 * 认证与用户身份工具
 *
 * 背景：
 *   后端用 X-Username 请求头做数据归属隔离（非认证手段），
 *   认证通过 Authorization: Bearer <JWT> 完成。
 *   登录成功后由 LoginPage 把 token 与用户名写入 localStorage，
 *   此前各组件散落着 'ai_teacher_token' / 'ai_teacher_user' 魔法字符串，
 *   统一收敛到本模块，避免键名不一致导致身份丢失。
 */

/** localStorage 键名（全项目唯一定义处） */
export const TOKEN_KEY = 'ai_teacher_token';
export const USER_KEY = 'ai_teacher_user';

/** 读取 JWT 令牌 */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

/** 保存 JWT 令牌 */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

/** 读取当前用户名（未登录或缺失时返回空串） */
export function getUser() {
  return localStorage.getItem(USER_KEY) || '';
}

/** 保存当前用户名 */
export function setUser(username) {
  localStorage.setItem(USER_KEY, username);
}

/** 清除登录态（退出登录 / 令牌失效时调用） */
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * 构造数据归属请求头
 *
 * X-Username 缺失时后端会把数据归属到 'anonymous'，
 * 所有需要按用户隔离的接口都必须带上该请求头。
 */
export function getOwnerHeader(username) {
  return { 'X-Username': username || getUser() || 'anonymous' };
}

/**
 * 解析 JWT payload（不验签，仅用于读取用户名等展示信息）
 *
 * 参数：
 *   token: string - 登录时后端返回的 JWT
 * 返回：
 *   object - payload 对象；解析失败返回空对象
 */
export function parseJwt(token) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch (e) {
    return {};
  }
}
