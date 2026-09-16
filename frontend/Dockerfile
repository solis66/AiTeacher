# ===== build 阶段：构建 Vue 静态产物 =====
FROM node:18-alpine AS build
WORKDIR /app

# 先装依赖（利用层缓存）
COPY package*.json ./
RUN npm install

# 拷贝源码并构建（vite 输出到 dist/）
COPY . .
RUN npm run build

# ===== serve 阶段：Nginx 托管静态文件 + 反代后端 =====
FROM nginx:1.27-alpine

# 站点配置（静态资源 + /api 等后端路径反代到 backend:8501）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 前端构建产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]