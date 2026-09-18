# 部署手册：前端 Vercel + 后端 Docker

> 目标：把 AITeacher 的前后端真正跑在公网上。
> 结论：**前端上 Vercel，后端必须用 Docker 跑在长期运行的服务器上**，两边用 `frontend/vercel.json` 的 rewrites 打通。
> 前端代码**一行都不用改**——全站请求都是相对路径（`/chat`、`/api/review/...`），靠代理转发，天然无跨域。

---

## 一、为什么后端不能部署到 Vercel

Vercel 的 Serverless Function 与本项目后端的运行形态冲突，不是配置问题：

| 后端实际依赖 | Vercel 函数环境 |
|:---|:---|
| `backend/history/*.md` 会话记录、`backend/data/reviews/reviews.sqlite3` + 上传的作文图片、`backend/chroma_db/` 向量库 | 只有 `/tmp` 可写、且实例随时回收，重启即丢 |
| 一次 AI 批改可能跑几十秒，前端 axios 超时设的是 120s | 函数有执行时长上限，长任务被截断 |
| `/chat?stream=true` 走 SSE 逐 token 推送 | 需要长连接 + 流式响应，Serverless 上易被缓冲/中断 |
| `chromadb` + `onnxruntime` + `pymupdf` + `reportlab` 全量依赖 | 远超函数体积上限 |
| 启动时后台线程预热检索索引（`consult_context.initialize()`） | 无常驻进程，冷启动每次重来 |

所以：**Vercel 只放前端静态产物，后端用容器跑。**

---

## 二、后端部署（Docker）

### 2.1 准备环境变量

`docker-compose.yml` 的 `env_file` 指向**仓库根目录**的 `.env`，而后端本身的 `.env` 在 `backend/` 下，部署时要复制过去：

```bash
cp backend/.env .env
```

需要的变量（按用途分组）：

| 变量 | 必填 | 说明 |
|:---|:---|:---|
| `DASHSCOPE_API_KEY` | ✅ | 通义千问密钥，缺失则启动校验直接 exit(1) |
| `PG_HOST` / `PG_PORT` / `PG_DB` / `PG_USER` / `PG_PASSWORD` | ✅ | 登录注册用的 PostgreSQL（当前指向 Supabase pooler） |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | 可选 | 批改工作台的图片 OCR；不配则上传图片走降级 |
| `PORT` | 容器内已设 8501 | `api.py` 读取，默认 8501 |
| `FLASK_DEBUG` | 已设 0 | `1` 会开 debug，**生产别开** |
| `REVIEW_FONT_PATH` | 可选 | 导出 PDF 的中文字体路径 |

> `.env` 已在 `.gitignore` 里，**不要提交**。

### 2.2 路线 A：自有 Linux 服务器（国内访问最快，推荐）

```bash
git clone https://github.com/solis66/AiTeacher.git
cd AiTeacher
cp backend/.env .env
docker compose up -d --build

# 查看状态（首次构建要装 chromadb/onnxruntime，耐心等）
docker compose ps
docker compose logs -f backend

# 后端健康检查（200 = AI 就绪；503 = 服务活着但模型未就绪，去查密钥）
curl -s http://127.0.0.1/health
```

- 前端容器用 Nginx 监听 **80**，既托管静态产物又反代后端接口 → **一台机器就能跑完整站**。
- 安全组放行 80。要 HTTPS 就用 `certbot` / `acme.sh` / 云厂商免费证书，或直接挂云 CDN。
- 这条路其实不需要 Vercel，适合「想给同学/导师一个地址直接打开」的场景。

### 2.3 路线 B：Render（仓库里已有 `render.yaml`）

Render 面板 → **New → Blueprint** → 选 `solis66/AiTeacher`。
`render.yaml` 已经声明好 Docker 运行时、`dockerContext: .`、`healthCheckPath: /health`。
在面板里手填 `sync: false` 的密钥（`DASHSCOPE_API_KEY`、`PG_PASSWORD`、阿里云 OCR 两个 Key）。
免费版 15 分钟无请求会休眠，正式演示建议升 starter。

### 2.4 路线 C：Railway / Fly.io

直接指向 `backend/Dockerfile`，构建上下文必须设为**仓库根**（Dockerfile 里是 `COPY backend/xxx`）。
**务必挂持久卷**到 `/app/history`、`/app/data/reviews`、`/app/chroma_db`，否则每次发布数据归零。

### 2.5 容器重建不丢数据（已在 compose 里配好）

```yaml
volumes:
  - ./backend/history:/app/history
  - ./backend/data/reviews:/app/data/reviews
  - ./backend/chroma_db:/app/chroma_db
```

`chroma_db` 尤其重要——重建会触发全量重新 embedding，慢且烧 API 额度。

---

## 三、前端部署（Vercel）

### 3.1 第一步：把后端域名填进 `frontend/vercel.json`

文件里所有 `https://YOUR-BACKEND-DOMAIN` 都要替换成**你后端真实的公网 HTTPS 地址**（不带结尾斜杠），例如 `https://api.yourdomain.com`。

**忘了改 = 前端所有接口 404**，这是最容易漏的一步。

它做的事：把 `/api/*`、`/chat`、`/login`、`/register`、`/get_history` 等前缀转发到后端，等价于本地开发时 `vite.config.js` 里的 proxy，只不过跑在 Vercel 边缘节点上。因为浏览器看到的仍是同源地址，所以**不涉及跨域，也不需要在 Vercel 配任何 CORS**。

### 3.2 第二步：导入项目

Vercel 面板 → **Add New → Project** → 选 `solis66/AiTeacher`，然后：

| 配置项 | 值 |
|:---|:---|
| **Root Directory** | `frontend` ← 关键，必须改 |
| Framework Preset | Vite（自动识别） |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | `npm ci`（仓库里有 `package-lock.json`） |

点 Deploy，几十秒出结果。之后每次 push 到 `main` 自动重新部署。

### 3.3 或者用 CLI

```bash
npm i -g vercel
cd frontend
vercel login
vercel --prod
```

首次会问 root directory 等，回答与上表一致。

---

## 四、上线验收清单

按顺序做，哪一步失败就停在哪：

1. **后端活着**
   `curl -s https://后端域名/health` → 返回 `{"status":"healthy",...}`。
   若 503，先解决密钥问题（`curl https://后端域名/config/check` 能给出具体哪项没过）。
2. **静态站点出来了**
   打开 `https://你的项目.vercel.app` → 看到登录页。
3. **注册通**（验证代理是否真的生效）
   注册一个 11 位手机号账号 → 应返回 JSON 提示。**如果返回的是 HTML**，说明 rewrites 没生效或域名没改对。
4. **登录 + 流式咨询**（验证 SSE）
   登录后问一句「怎么写好记叙文的开头」，回答应该**逐字冒出来**。
   如果是「停顿很久然后整段蹦出来」，说明流式被 Vercel 平台层缓冲了，见 5.1。
5. **批改工作台**（验证图片与导出）
   上传一张作文图片 → 缩略图能显示 → 导出 PDF 能下载。
   `<img>` 走的是 `/api/review/{id}/page/{file}?owner=xxx`，同样经 rewrites，不生效会白图。

---

## 五、已知风险与兜底方案

### 5.1 SSE 流式被 Vercel 缓冲（最需要留意的点）

rewrites 是 Vercel 边缘层的反向代理，绝大多数情况下能透传流式，但平台层缓冲时有发生。
**如果第 4 步不流式**，兜底做法是让咨询请求绕过 Vercel 直连后端——后端 `CORS(app)` 已全开，直连可用：

`frontend/src/components/MainPage.vue` 第 305 行附近：

```js
const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const res = await fetch(`${API_BASE}/chat`, { ... });
```

然后在 Vercel 项目里加环境变量 `VITE_API_BASE_URL=https://后端域名`（改完要重新部署）。
Node 侧的图像/导出地址仍走 rewrites，不受影响。

### 5.2 `*.vercel.app` 在国内网络的连通性

默认域名在国内常被 DNS 污染/连接不稳，**演示前一定实测**。
稳妥做法：在 Vercel 绑定自己的域名（Project → Settings → Domains），用国内可解析的 DNS。
如果目标用户全在国内，直接走 2.2 的单机 Docker 方案反而更省心。

### 5.3 Vercel 免费额度与非商用条款

Hobby 计划的带宽与调用次数有上限，且条款上限于非商业用途。毕设演示没问题，对外运营要换 Pro。

### 5.4 后端用的是 Flask 内置服务器

`api.py` 结尾是 `app.run(...)`，也就是 Werkzeug 开发服务器：单进程、并发差，多人同时提问会排队。
演示够用，要抗并发可以在 `backend/requirements.txt` 加 `gunicorn==23.0.0`，并把 Dockerfile 的 CMD 换成：

```dockerfile
# Chroma 与内存都不适合多进程，必须单 worker 多线程
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "8", \
     "--timeout", "600", "-b", "0.0.0.0:8501", "api:app"]
```

注意 `--threads` 与 `-k gthread` 是 SSE 能用的前提；`-w 1` 是因为 Chroma 多进程并发写会出问题，8GB 内存也扛不住多份副本。

---

## 六、本次一并修掉的三个部署阻断问题

| 文件 | 问题 | 影响 |
|:---|:---|:---|
| `docker-compose.yml` | backend 的 `context: ./backend`，但 `backend/Dockerfile` 里写的是 `COPY backend/xxx` | 构建直接失败（找不到文件），`docker compose up` 根本起不来 |
| `frontend/nginx.conf` | 反代 location 正则漏了 `/register`（及 `/config`） | 部署后注册接口返回 404 |
| `frontend/vite.config.js` | 开发代理同样漏了 `/register` | **本地开发时注册就是坏的**（请求落到 vite 上返回 index.html） |
| `docker-compose.yml` | 没有数据卷 | 每次 `--build` 重建容器，批改记录与向量库全丢 |

---

## 七、附：后端服务器选型（轻量应用服务器）

**结论：可以，而且对这个项目是最合适的形态。** 单体 Flask、数据全在本地盘、没有集群需求，轻量服务器刚好对口。下面是按实测数据给的配置建议。

### 7.1 资源实测（本机口径，可直接换算）

| 项目 | 实测值 | 说明 |
|:---|:---|:---|
| `backend/.venv/site-packages` | 549.8 MB / 27172 文件 | 全是预编译 wheel，Linux 下量级一致 |
| 预估镜像体积 | **约 0.8–1 GB** | python:3.11-slim(≈120MB) + 依赖 + 代码 |
| `backend/chroma_db/` | 3.5 MB | 向量库很小 |
| `backend/data/reviews/` | 24.9 MB / 36 文件 | 批改记录 + 上传的作文图片 |
| 嵌入模型 | **本地不加载** | 走 DashScope `text-embedding-v1` API（`model/factory.py` 用 `OpenAIEmbeddings`），所以不吃内存、不占 CPU |

内存是唯一需要认真掂量的项：运行期 Python + Flask + langchain + chromadb 的常驻约 **400–700 MB**，
但 **`docker build` 期间峰值会到 1–1.5 GB**（pip 解压大 wheel + 层合并）。

### 7.2 配置建议

| 项目 | 建议 | 理由 |
|:---|:---|:---|
| CPU / 内存 | **2 核 4G 首选**；2 核 2G 可用，但必须加 swap | 2G 机器构建镜像时有 OOM 风险 |
| CPU 架构 | **必须选 x86_64，别为省钱选 ARM** | chromadb 的 hnswlib、onnxruntime 都依赖预编译 wheel，aarch64 上容易退化成源码编译甚至构建失败 |
| 系统盘 | 40 GB 起 | 镜像 1GB + 构建中间层 + 数据卷，富余 |
| 带宽 | 3 Mbps 勉强，**建议 5 Mbps 以上** | 手机拍的作文图 2–5 MB，3 Mbps ≈ 375 KB/s，一张图要十几秒，学生体感很差 |
| 流量包 | 关注月流量上限 | AI 咨询是纯文本、流量极小；**批改上传的图片才是大头** |
| 地域 | 大陆节点 → 需 ICP 备案；香港节点 → 免备案 | 见 7.3 |

### 7.3 大陆节点 vs 香港节点

- **大陆节点**：国内访问快、带宽便宜，但**域名必须完成 ICP 备案**才能用 80/443 对外提供 Web 服务。
  备案本身免费，但要等审核周期，且域名需挂在该云厂商名下。
- **香港节点**：免备案、当天可上线，代价是国内访问延迟更高（30–80 ms）且带宽通常更小更贵。
- 只是给导师/答辩演示用、图省事 → 香港节点；要长期给真实学生用 → 大陆节点 + 备案。

### 7.4 服务器初始化（Ubuntu 22.04 为例）

```bash
# 1) 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker

# 2) 2G 内存的机器必做：加 2G swap，否则构建阶段容易被 OOM Killer 干掉
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 3) 拉代码并准备环境变量
git clone https://github.com/solis66/AiTeacher.git && cd AiTeacher
cp backend/.env .env        # 或用 vi 直接写

# 4) 构建并启动（首次构建 5–10 分钟，瓶颈在 pip）
docker compose up -d --build
docker compose logs -f backend
curl -s http://127.0.0.1/health
```

安全组只需放行 **22**（SSH）和 **80**（Web）；数据库在 Supabase 上，不需要放行 5432。

### 7.5 上 HTTPS 的正确姿势（有个端口冲突的坑）

**坑**：`docker-compose.yml` 里 frontend 已经绑定了宿主机 80 端口，所以宿主机上再装 Nginx 会抢不到端口，
`certbot --nginx` 那套常规流程直接失效。

正确做法二选一：

**方案 A：宿主机终止 TLS（推荐，可控）**
1. 把 compose 里 frontend 的端口改成 `"8080:80"`，让容器退到 8080；
2. 宿主机装 Nginx，监听 80/443，`proxy_pass http://127.0.0.1:8080;`；
3. `sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d 你的域名`。

**方案 B：云厂商 CDN / 负载均衡托管证书**
源站指向服务器 80，证书由云平台托管。省事，但要额外付费，且回源要配好。

**如果暂时没有域名**：走 Vercel rewrites 时，浏览器只和 Vercel 通信，代理发生在服务端，
所以**后端只有 HTTP + IP 也能先把链路跑通**，不必一开始就折腾证书。正式对外再补 HTTPS。

### 7.6 一个容易被忽略的成本

前端放 Vercel、后端放服务器时，**所有批改图片的流量都要经 Vercel 中转**，
会消耗 Vercel Hobby 计划的每月带宽额度。

如果批改图片量注定很大，两个选择：
- 把前端也放到同一台轻量服务器上（走 2.2 的单机 docker compose），图片流量完全不经过 Vercel；
- 或让图片请求绕过 rewrites，直接指向后端域名（但会引入跨域，需要后端 CORS 放行，目前 `CORS(app)` 是全开的，可行）。

---

## 八、腾讯云轻量服务器实操（Ubuntu 24.04）

> 下文用 `<服务器IP>` 代替真实公网 IP，执行时替换即可。

### 8.1 实例参数确认

| 项目 | 实际 | 结论 |
|:---|:---|:---|
| CPU / 内存 | 2 vCPU / 4 GiB | ✅ 正好卡在推荐配置上，无需调整 |
| 系统盘 | 50 GiB | ✅ 镜像+数据约 5GB，富余 |
| 架构 | x86_64 | ✅ 避开了 ARM 的 wheel 坑 |
| 地域 | 华南3（广州） | 大陆节点：**绑域名必须 ICP 备案**；用公网 IP 直接访问 80 不受影响 |
| 到期时间 | 一个月后 | ⚠️ **别撞上答辩，提前续费** |

### 8.2 第一步：本机连上去

控制台「重置密码」设好 root 密码（或绑定 SSH 密钥），然后本地终端：

```bash
ssh root@<服务器IP>
```

### 8.3 第二步：服务器初始化

```bash
# 1) Docker
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# 2) swap：4G 内存本可不加，但 docker build 峰值 1~1.5GB，加 2G 兜底更稳
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 3) 确认
docker --version && free -h
```

### 8.4 第三步：拉代码

```bash
cd /root
git clone https://github.com/solis66/AiTeacher.git
cd AiTeacher
```

国内服务器访问 GitHub 可能很慢。若卡住，改用镜像再切回官方：

```bash
git clone https://gitclone.com/github.com/solis66/AiTeacher.git
cd AiTeacher
git remote set-url origin https://github.com/solis66/AiTeacher.git
```

### 8.5 第四步：把环境变量传上去

**在本地**（不是服务器上）执行：

```bash
scp backend/.env root@<服务器IP>:/root/AiTeacher/.env
```

注意放到**仓库根目录**，不是 `backend/` 下——`docker-compose.backend.yml` 的 `env_file` 指向仓库根。

### 8.6 第五步：构建并启动（只跑后端）

```bash
docker compose -f docker-compose.backend.yml up -d --build
docker compose -f docker-compose.backend.yml logs -f backend
```

首次构建 5–10 分钟，瓶颈在 pip（已默认走腾讯云内网源）。
日志出现 Flask 启动信息后 `Ctrl+C` 退出日志跟踪（容器仍在后台跑）。

### 8.7 第六步：验证

```bash
# 服务器上
curl -s http://127.0.0.1/health

# 本地终端
curl -s http://<服务器IP>/health
```

返回 `{"status":"healthy",...}` 就成了。若返回 503，说明服务活着但 AI 未就绪（密钥问题）：

```bash
curl -s http://<服务器IP>/config/check
```

**80 端口从外网不通**，按顺序查：
1. 腾讯云控制台 → 该实例 → **防火墙**页，确认 80 已放行（默认有）；
2. 服务器上 `ss -lntp | grep :80`，确认端口在监听；
3. `docker ps` 确认容器是 `Up` 而不是反复重启。

### 8.8 第七步：填进 vercel.json

把 `frontend/vercel.json` 里所有 `https://YOUR-BACKEND-DOMAIN` 替换成 `http://<服务器IP>`，提交推送，Vercel 会自动重新部署。

> ⚠️ Vercel 对 http:// 的 rewrite 目标行为不保证。部署后如果接口报 502/404，
> 就是平台要求 https 了，按 7.5 给后端补域名 + 证书即可。

### 8.9 日常运维

```bash
# 看日志
docker compose -f docker-compose.backend.yml logs -f backend

# 更新代码后重新部署（数据卷不受影响）
cd /root/AiTeacher && git pull && docker compose -f docker-compose.backend.yml up -d --build

# 重启 / 停止
docker compose -f docker-compose.backend.yml restart
docker compose -f docker-compose.backend.yml down
```

**数据备份**：`backend/history/`、`backend/data/reviews/`、`backend/chroma_db/` 全在这块盘上，
没有冗余。建议在控制台开启**自动快照**，或定期拉回本地：

```bash
scp -r root@<服务器IP>:/root/AiTeacher/backend/data/reviews ./backup/
```

---

## 九、阿里云 ECS 实操（Ubuntu 24.04 · 当前使用）

> 这台机器与第八章的腾讯云**不是同一台**，差异集中在三点：登录用户是 `admin` 而非 `root`、
> 镜像源要用阿里云、安全组放行入口在 ECS 控制台。下文用 `<公网IP>` 代替真实 IP。

### 9.1 实例与登录方式确认

| 项目 | 实际 | 说明 |
|:---|:---|:---|
| 云厂商 / 系统 | 阿里云 ECS · Ubuntu 24.04.2 LTS | 内核 6.8，x86_64 |
| 登录用户 | **`admin`**（非 root） | 所有特权命令要 `sudo`，或先 `sudo -i` 提权 |
| 系统盘 | 48.85 GiB（已用 5.43 GiB） | ✅ 富余，镜像约 1 GB |
| 登录方式 | 控制台网页 Cloud Shell | 也可在本地 `ssh admin@<公网IP>` |
| 主机名 | `iZ7xv46h7zafqjz9j0ycycZ` | 阿里云 ECS 默认命名 |

> 网页终端底部那条「AI 命令栏」是控制台自带助手，**用不上，直接在 Shell 里粘贴命令即可**。

### 9.2 第一步：提权并确认环境

```bash
# 提到 root，后续命令不必再逐个加 sudo
sudo -i

# 确认资源与磁盘
free -h          # 关注 Mem，2G 就要做 9.4 的 swap
df -h /          # 关注 Avail

# 确认 apt 源（阿里云镜像默认就指向内网源，通常无需改动）
grep -rh '^URIs\|^deb ' /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null | head -5
```

### 9.3 第二步：安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker --version && docker compose version
```

**如果 `get.docker.com` 慢或超时**，改用阿里云自己的 docker-ce 镜像（在阿里云内网最快）：

```bash
apt-get update && apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.aliyun.com/docker-ce/linux/ubuntu noble stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

> Docker 24+ 自带 `docker compose`（v2 插件）；若只装到旧版，把后文命令里的 `docker compose`
> 换成 `docker-compose`（中间是短横线）。

### 9.4 第三步：加 swap（2G 内存必做，4G 可选）

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h   # 确认 Swap 一行有值
```

### 9.5 第四步（容易漏）：给 Docker 配镜像加速

**这一步在阿里云上是决定性的**。基础镜像 `python:3.11-slim` 要从 Docker Hub 拉，国内直连经常
慢到超时或直接失败——它不是 apt/pip 源能救的，必须走 registry 加速。

阿里云给每个账号一个**专属免费加速地址**：控制台 → 搜索「容器镜像服务 ACR」→ 左侧「镜像工具」→
「镜像加速器」，复制形如 `https://xxxx.mirror.aliyuncs.com` 的地址，然后：

```bash
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://<你的专属地址>.mirror.aliyuncs.com"]
}
EOF
systemctl restart docker
docker info | grep -A3 'Registry Mirrors'
```

（若已有 `/etc/docker/daemon.json`，**先备份再合并 `registry-mirrors` 字段**，别整个覆盖。）

### 9.6 第五步：拉代码

克隆到 `admin` 的家目录，避免后面 `scp` 传文件时的属主/权限问题：

```bash
cd /home/admin
git clone https://github.com/solis66/AiTeacher.git
cd AiTeacher
```

国内访问 GitHub 可能很慢。**卡住就换镜像**（不要用 `--depth 1`，实测会卡死）：

```bash
git clone https://gitclone.com/github.com/solis66/AiTeacher.git
cd AiTeacher
git remote set-url origin https://github.com/solis66/AiTeacher.git
```

> 仓库里的 `backend/Dockerfile`、`docker-compose.backend.yml` 是部署必需的修复版，
> **必须先在本机 commit + push，服务器才拉得到**。

### 9.7 第六步：把 `.env` 放上去

必须在**仓库根目录**（不是 `backend/` 下），`docker-compose.backend.yml` 的 `env_file` 指向那里。

**方式 A（推荐）**：在**本地**终端执行——

```bash
scp backend/.env admin@<公网IP>:/home/admin/AiTeacher/.env
```

**方式 B**：直接在网页终端里粘贴（`nano` 或 heredoc，注意 `<<'EOF'` 的引号别丢，否则 `$` 会被 shell 展开）：

```bash
cat > /home/admin/AiTeacher/.env <<'EOF'
DASHSCOPE_API_KEY=...
PG_HOST=...
# ...其余变量
EOF
chmod 600 /home/admin/AiTeacher/.env
```

### 9.8 第七步：安全组放行 80

**阿里云 ECS 默认安全组通常只放行 22，不放行 80**，这一步不漏否则外网永远连不上：

控制台 → **云服务器 ECS** → 实例 → 点进该实例 → **安全组** → 「配置规则」→ **入方向** →
「手动添加」：

| 项 | 值 |
|:---|:---|
| 协议类型 | 自定义 TCP |
| 端口范围 | `80/80` |
| 授权对象 | `0.0.0.0/0` |

> 服务器本机若有 ufw/firewalld，一并确认：`ufw status` 应为 inactive 或已放行 80。
> 阿里云 Ubuntu 镜像默认不启用 ufw，一般不用管。

### 9.9 第八步：构建并启动（只跑后端）

```bash
cd /home/admin/AiTeacher
docker compose -f docker-compose.backend.yml up -d --build
docker compose -f docker-compose.backend.yml logs -f --tail 50 backend
```

首次构建 5–10 分钟（pip 装约 550 MB 依赖，已走阿里云内网源）。看到 Flask 启动日志后
`Ctrl+C` 退出日志跟踪（容器仍在后台跑）。

### 9.10 第九步：验证

```bash
# 服务器上
curl -s http://127.0.0.1/health

# 本地终端
curl -s http://<公网IP>/health
```

返回 `{"status":"healthy",...}` 即成功。503 表示服务活着但 AI 未就绪：

```bash
curl -s http://<公网IP>/config/check    # 直接告诉你哪项密钥没过
```

**外网不通时按顺序排查**：

```bash
docker ps                                    # 容器是否 Up（反复重启 = 看日志）
ss -lntp | grep ':80'                        # 端口是否在监听
docker compose -f docker-compose.backend.yml logs --tail 100 backend
```

再回头确认 9.8 的安全组规则已生效（阿里云安全组修改即时生效，无需重启实例）。

### 9.11 第十步：把后端地址填进 `frontend/vercel.json`

把所有 `https://YOUR-BACKEND-DOMAIN` 换成 `http://<公网IP>`，提交推送，Vercel 自动重新部署。

> ⚠️ Vercel 对 `http://` 的 rewrite 目标行为不保证。若部署后接口报 502/404，
> 就是平台要求 https 了——按 7.5 补域名 + 证书，并把容器端口退到 8080。

### 9.12 日常运维

```bash
cd /home/admin/AiTeacher

# 更新代码后重新部署（数据卷不受影响）
git pull && docker compose -f docker-compose.backend.yml up -d --build

# 日志 / 重启 / 停止
docker compose -f docker-compose.backend.yml logs -f backend
docker compose -f docker-compose.backend.yml restart
docker compose -f docker-compose.backend.yml down
```

**本机磁盘占用**：镜像约 1 GB + 构建缓存。磁盘紧张时清理：

```bash
docker system df          # 先看占用
docker builder prune -f   # 清构建缓存（安全，只删中间层）
```

