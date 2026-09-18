# ===== build 阶段：构建 Vue 静态产物 =====
FROM node:18-alpine AS build
WORKDIR /app

# npm 源可覆盖：国内服务器直连 registry.npmjs.org 极慢甚至超时。
# 换源用环境变量覆盖即可，不必改本文件：
#   NPM_REGISTRY=https://registry.npmjs.org docker compose up -d --build
ARG NPM_REGISTRY=https://registry.npmmirror.com

# 先装依赖（利用层缓存：只改源码时这一层会命中缓存，不用重装）
COPY package*.json ./

# ⚠️ 必须同时改写 package-lock.json 里的 resolved 域名。
# lock 文件里写死了 146 处 https://registry.npmjs.org/...，npm ci 会直接按这些 URL 下载，
# 只传 --registry 参数对它无效 —— 表现为「换了源还是很慢/超时」，很容易误判成源本身不行。
# npmmirror 与官方源的包路径结构一致，替换域名即可。
RUN set -eux; \
    if [ -f package-lock.json ]; then \
        sed -i "s|https://registry.npmjs.org|${NPM_REGISTRY}|g" package-lock.json; \
        npm ci --no-audit --no-fund --registry="${NPM_REGISTRY}" \
        || npm install --no-audit --no-fund --registry="${NPM_REGISTRY}"; \
    else \
        npm install --no-audit --no-fund --registry="${NPM_REGISTRY}"; \
    fi

# 拷贝源码并构建（vite 输出到 dist/）
COPY . .

# 限制 Node 堆上限：本项目 src 仅约 180KB，1G 绰绰有余；
# 不设上限时 Node 在 4G 机器上可能贪心吃满内存，把同在跑的后端容器一起拖慢。
RUN NODE_OPTIONS=--max-old-space-size=1024 npm run build

# ===== serve 阶段：Nginx 托管静态文件 + 反代后端 =====
FROM nginx:1.27-alpine

# 站点配置（静态资源 + /api 等后端路径反代到 backend:8501）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 前端构建产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
