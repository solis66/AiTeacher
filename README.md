# AITeacher - AI作文批改系统
---

## 项目概述 | Project Overview

AITeacher 是一个由课程项目变成毕业设计的项目，主要面向中学生语文作文的 AI 作文批改工作台。系统采用 RAG（检索增强生成）技术，依据标准化评分标准自动完成作文初批——多维度评分、总体评价与改进建议一次生成；用户可以在批改工作台中对 AI 结果进行复核、修订与精批，把重复性劳动交给 AI，把精力留给因材施教。

同时，系统内置 **AI 咨询助手**：基于教研知识库与历史批改学情的检索问答，帮助用户快速解答作文教学问题、了解写作薄弱点。


### 主要核心功能 | Core Features
- **批改结果工作台**：

- **AI咨询老师**


---

## 技术栈 | Technology Stack

### 后端 | Backend
- **框架**: Flask 3.x
- **语言**: Python 3.11+
- **存储**: Chroma 向量库（RAG 检索）+ SQLite（批改记录）+ JSON 文件（会话/用户数据）
- **AI 技术**: RAG（检索增强生成）+ ReactAgent（工具调用代理）

### 前端 | Frontend
- **框架**: Vue 3.3+
- **构建工具**: Vite 4.4+
- **HTTP 客户端**: Axios（统一封装拦截器）
- **样式**: CSS3

### 项目结构 | Project Structure

```
AiTeachers/
├── backend/                # Python 后端（自包含，可独立部署）
│   ├── agent/              # AI 代理模块（ReactAgent、工具定义、中间件）
│   ├── config/             # YAML 配置文件（代理/RAG/提示词/向量库）
│   ├── data/               # 评分标准、教研知识库与批改运行数据
│   ├── middlewares/        # 请求日志等中间件
│   ├── model/              # 模型工厂（LLM 与向量模型初始化）
│   ├── prompts/            # 提示词模板
│   ├── rag/                # RAG 检索服务（向量库、知识加载、学情索引）
│   ├── routes/             # API 路由（批改工作台、作文）
│   ├── services/           # 业务服务（批改、咨询、文档处理）
│   ├── utils/              # 工具函数（路径、安全、评分计算、文本处理等）
│   ├── api.py              # Flask 后端入口
│   ├── settings.py         # 配置管理
│   └── requirements.txt    # 后端依赖清单（精确锁定版本）
├── frontend/               # Vue3 + Vite 前端（自包含）
│   ├── src/
│   │   ├── api/            # axios 统一封装（拦截器注入认证与用户标识）
│   │   ├── components/     # Vue 组件
│   │   │   ├── review/     # 批改工作台（列表栏/画布/评分面板/润色对比）
│   │   │   ├── ChatHistory.vue     # 对话消息流（含批改入口卡）
│   │   │   ├── InputArea.vue       # 输入区（文本/附件/年级选择）
│   │   │   ├── LoginPage.vue       # 登录页
│   │   │   ├── MainPage.vue        # 主页面（对话首页与工作台切换）
│   │   │   └── ...                 # 其余展示组件
│   │   ├── utils/          # 前端工具（认证、时间格式化、批改 URL）
│   │   ├── App.vue         # 主应用组件
│   │   └── main.js         # 入口文件
│   ├── index.html          # HTML 入口
│   ├── vite.config.js      # Vite 配置（开发代理指向后端 8501）
│   └── vitest.config.js    # 单元测试配置
└── docs/                   # 设计文档
```

---

## 安装指南 | Installation Guide

### 环境要求 | Requirements

| 组件 | 版本要求 | Component | Version |
|:---|:---|:---|:---|
| Python | 3.11+ | Python | 3.11+ |
| Node.js | 18 LTS+ | Node.js | 18 LTS+ |
| npm | 8+ | npm | 8+ |

> 说明：评分标准的 Word COM 提取依赖 Windows + Microsoft Word 环境；非 Windows 平台自动降级为内置评分标准文本。
> Note: Word-based criteria extraction relies on Windows + Microsoft Word; other platforms fall back to the built-in criteria text.

### 安装步骤 | Installation Steps

#### 1. 克隆项目 | Clone the Repository

```bash
git clone https://github.com/solis66/AiTeacher.git
cd AiTeacher
```

#### 2. 安装后端依赖 | Install Backend Dependencies

```bash
cd backend

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # Linux/Mac

# 安装依赖（版本清单见 requirements.txt）
pip install -r requirements.txt
```

#### 3. 安装前端依赖 | Install Frontend Dependencies

```bash
cd ../frontend
npm install
```

---

## 使用说明 | Usage

### 启动后端服务 | Start Backend Service

```bash
cd backend
python api.py
# 或使用虚拟环境 | Or with the project venv:
# .venv\Scripts\python.exe api.py
```

后端服务将在 `http://localhost:8501` 启动（前端开发代理指向该端口）。

The backend service will start at `http://localhost:8501` (the frontend dev proxy targets this port).

### 启动前端开发服务器 | Start Frontend Development Server

```bash
cd frontend
npm run dev
```

前端服务将在 `http://localhost:3000` 启动。

The frontend service will start at `http://localhost:3000`.

### 构建前端生产版本 | Build Frontend for Production

```bash
cd frontend
npm run build
```

构建产物将生成在 `frontend/dist/` 目录。

Build output will be in the `frontend/dist/` directory.





## 贡献指南 | Contributing

欢迎贡献代码！请遵循以下步骤：

Contributions are welcome! Please follow these steps:

1. Fork 项目 | Fork the project
2. 创建功能分支 | Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. 提交更改 | Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 | Push to the branch (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request | Create a Pull Request

### 代码规范 | Code Standards

- Python代码遵循PEP 8规范 | Python code follows PEP 8
- Vue组件使用统一的命名规范 | Vue components use consistent naming conventions
- 提交信息清晰描述更改内容 | Commit messages clearly describe changes

---


## 联系方式 | Contact

如有问题或建议，请通过以下方式联系：

For questions or suggestions, please contact:

- 邮箱 | Email: 2093125624@qq.com
- GitHub: [solis66](https://github.com/solis66)

---

*Made with ❤️ by solis66
