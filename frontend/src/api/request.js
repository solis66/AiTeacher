/**
 * axios 统一封装
 *
 * 此前各组件直接 import axios 裸调接口，导致：
 * 1. X-Username / Authorization 请求头在每个调用点手拼，遗漏会造成数据归属错乱；
 * 2. 错误日志格式各异，排查问题困难。
 *
 * 本模块提供统一实例：
 * - 请求拦截器自动注入 Authorization（已登录时）与 X-Username（调用方未显式
 *   指定时）。调用方显式传入的请求头优先级更高，可覆盖默认注入。
 * - 响应拦截器统一打印错误日志，错误原样抛出，由调用方决定如何提示用户。
 *
 * 注意：<img src> 无法携带自定义请求头，相关图片地址仍需按
 * utils/reviewUrl.js 的方式把 owner 拼进查询参数。
 */

import axios from 'axios';
import { getToken, getUser } from '../utils/auth.js';

/** 创建统一实例（baseURL 留空，路径直接写 /api/* 等相对路径，走 vite 代理） */
const request = axios.create({
  timeout: 120000 // 批改与咨询可能耗时较长（AI 生成 + 重试），默认超时不够
});

// 请求拦截器：注入认证与数据归属请求头
request.interceptors.request.use((config) => {
  // Authorization：已有 token 且调用方未显式提供时注入
  const token = getToken();
  if (token && !config.headers.get('Authorization')) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }

  // X-Username：数据归属标识，调用方显式提供时（如老师端指定学生）不覆盖
  if (!config.headers.get('X-Username')) {
    config.headers.set('X-Username', getUser() || 'anonymous');
  }

  return config;
});

// 响应拦截器：统一错误日志（不吞错误，调用方按需提示）
request.interceptors.response.use(
  (response) => response,
  (error) => {
    const { config, response } = error;
    const url = config?.url || '未知接口';
    const status = response?.status ?? '无响应';
    const message = response?.data?.message || response?.data?.error || error.message;
    console.error(`[API] ${config?.method?.toUpperCase() || 'GET'} ${url} 失败 (${status}): ${message}`);
    return Promise.reject(error);
  }
);

export default request;
