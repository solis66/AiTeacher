# AITeacher - AI作文批改系统

<!-- 项目徽章 -->
![GitHub](https://img.shields.io/github/license/yourusername/AiTeachers)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![Vue Version](https://img.shields.io/badge/vue-3.3%2B-green)
![Flask Version](https://img.shields.io/badge/flask-3.x-orange)
![Vite Version](https://img.shields.io/badge/vite-4.4%2B-purple)

---

## 项目概述 | Project Overview

AITeacher 是一个面向**初中语文老师**的 AI 作文批改效率工具。系统采用 RAG（检索增强生成）技术，依据标准化评分标准自动完成作文初批——多维度评分、总体评价与改进建议一次生成；老师再在批改工作台中对 AI 结果进行复核、修订与精批，把重复性劳动交给 AI，把精力留给因材施教。

同时，系统内置 **AI 咨询助手**：基于教研知识库与学生历史批改学情的检索问答，帮助老师快速解答作文教学问题、了解班级学生的写作薄弱点。

AITeacher is an AI-powered essay grading assistant designed for **middle school Chinese teachers**. Built on RAG (Retrieval-Augmented Generation) technology, it automatically produces a first-pass grading report — multi-dimensional scores, overall comments and improvement suggestions — against standardized scoring criteria. Teachers then review, refine and finalize the results in the grading workbench, letting AI handle the repetitive work while they focus on personalized instruction.

An integrated **AI consultation assistant** answers essay-teaching questions by retrieving from the teaching-research knowledge base and students' grading history, helping teachers quickly understand each student's writing weaknesses.

### 核心功能 | Core Features

| 功能 | 描述 | Feature | Description |
|:---|:---|:---|:---|
| 📝 **智能作文批改** | 自动识别作文体裁（议论文、记叙文、说明文），依据标准化作文评分标准进行多维度评分并生成批改报告 | **Intelligent Essay Grading** | Automatically detects essay types (Argumentative, Narrative, Expository) and produces a multi-dimensional grading report against standardized criteria |
| 🖼️ **多格式作文提交** | 支持直接输入文本，或上传手写作文图片/PDF 附件，由批改工作台统一处理 | **Multi-format Submission** | Accepts typed text or handwritten essay images/PDF attachments, processed uniformly by the grading workbench |
| 🖊️ **批改工作台** | 批改结果页面：原文页画布查看（缩放、旋转、翻页）、画笔批注与橡皮擦除、撤销/恢复、逐页下载，AI 评分支持人工修订覆盖 | **Grading Workbench** | Result page with canvas viewing (zoom, rotate, page navigation), pen annotations, eraser, undo/redo, per-page download; AI scores are manually adjustable |
| ✨ **润色对比** | AI 生成润色稿后以差异对比视图呈现，老师可直观看到逐句修改建议 | **Polish Diff** | AI-generated polished drafts are presented as diff views, showing sentence-level revisions at a glance |
| 🎓 **AI 咨询助手** | 面向老师的作文教学问答：检索教研知识库与学生历史批改学情，支持多轮对话与追问 | **AI Consultation Assistant** | Teaching Q&A for teachers: retrieves from the knowledge base and students' grading history, with multi-turn conversation support |
| 🔁 **异步批改与失败重试** | 批改任务异步执行（排队 → 识别 → 批改 → 完成），失败后可一键重试，无需重新上传材料 | **Async Grading & Retry** | Grading runs asynchronously (queued → recognizing → grading → done) with one-click retry that reuses uploaded materials |
| 📤 **批改结果导出** | 批改完成后可导出为pdf格式归档 | **Result Export** | Grading results can be exported to multiple formats for archiving |
| 📊 **历史记录** | 对话历史本地保存并同步服务器；批改记录按用户隔离，可随时回看 | **History Records** | Chat history is stored locally and synced to the server; grading records are user-isolated and always retrievable |

### 典型使用流程 | Typical Workflow

1. 老师登录后，在对话首页粘贴作文文本或上传手写作文图片，选择体裁（可留空由 AI 自动识别）；
2. 系统创建批改任务并在对话流中展示进度（批改中 → 完成入口）；
3. 点击进入**批改工作台**：对照原文逐页查看 AI 评分，修改分数、调整评语、添加画笔批注；
4. 需要时查看**润色稿差异对比**，或将批改结果导出归档；
5. 教学中遇到问题（如何讲评某类作文、某学生常见问题等），随时向 **AI 咨询助手**提问。

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
git clone https://github.com/yourusername/AiTeachers.git
cd AiTeachers
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

### 登录凭证 | Login Credentials

| 用户名 | 密码 | Username | Password |
|:---|:---|:---|:---|
| admin | 123456 | admin | 123456 |

---

## 支持的作文类型 | Supported Essay Types

| 类型 | 评分维度 | Type | Scoring Dimensions |
|:---|:---|:---|:---|
| **议论文** | 立意与中心、论点与论证、结构与层次、语言表达、例证与材料运用 | **Argumentative** | Theme, Arguments, Structure, Language, Evidence |
| **记叙文** | 立意与中心、选材与内容、结构与层次、语言表达、细节与表现、书写与规范 | **Narrative** | Theme, Content, Structure, Language, Details, Writing |
| **说明文** | 立意与中心、结构与层次、语言表达、方法与技巧、书写与规范 | **Expository** | Theme, Structure, Language, Methods, Writing |

---

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

## 许可证 | License

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 联系方式 | Contact

如有问题或建议，请通过以下方式联系：

For questions or suggestions, please contact:

- 邮箱 | Email: 2093125624@qq.com
- GitHub: solis66(https://github.com/solis66)

---

*Made with ❤️ by solis66
