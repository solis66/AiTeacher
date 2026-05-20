# AITeacher - AI作文批改系统

<!-- 项目徽章 -->
![GitHub](https://img.shields.io/github/license/yourusername/AiTeachers)
![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Vue Version](https://img.shields.io/badge/vue-3.3%2B-green)
![Flask Version](https://img.shields.io/badge/flask-2.0%2B-orange)
![Vite Version](https://img.shields.io/badge/vite-4.4%2B-purple)

---

## 项目概述 | Project Overview

AITeacher是一个基于人工智能的智能作文批改系统，旨在为学生提供专业、准确的作文批改服务。系统采用先进的RAG（检索增强生成）技术，能够自动识别作文类型并根据标准化评分标准进行批改。

AITeacher is an AI-powered intelligent essay grading system designed to provide professional and accurate essay evaluation services for students. The system utilizes advanced RAG (Retrieval-Augmented Generation) technology to automatically detect essay types and grade them according to standardized scoring criteria.

### 核心功能 | Core Features

| 功能 | 描述 | Feature | Description |
|:---|:---|:---|:---|
| 📝 **智能作文批改** | 自动识别作文类型（议论文、记叙文、说明文）并进行专业批改 | **Intelligent Essay Grading** | Automatically detects essay types (Argumentative, Narrative, Expository) and provides professional evaluation |
| 🎯 **多维度评分** | 从立意、结构、语言表达等多个维度进行评分 | **Multi-dimensional Scoring** | Scores essays from multiple dimensions including theme, structure, and language expression |
| 💡 **个性化建议** | 根据作文实际问题提供针对性的改进建议 | **Personalized Feedback** | Provides targeted improvement suggestions based on actual essay issues |
| 🔄 **对话交互** | 支持与AI助手进行自然语言对话咨询 | **Conversational Interaction** | Supports natural language conversations with AI assistant |
| 📊 **历史记录** | 保存批改历史，方便学生回顾和学习 | **History Records** | Saves grading history for review and learning |

---

## 技术栈 | Technology Stack

### 后端 | Backend
- **框架**: Flask 2.0+
- **语言**: Python 3.10+
- **数据库**: SQLite (Chroma DB for vector storage)
- **AI技术**: RAG (Retrieval-Augmented Generation)

### 前端 | Frontend
- **框架**: Vue 3.3+
- **构建工具**: Vite 4.4+
- **HTTP客户端**: Axios
- **样式**: CSS3

### 项目结构 | Project Structure

```
AiTeachers/
├── agent/              # AI代理模块
│   └── tools/          # 工具函数
├── config/             # 配置文件
├── data/               # 评分标准数据
├── dist/               # 前端构建产物
├── rag/                # RAG服务模块
├── routes/             # API路由
├── services/           # 业务服务
├── src/                # 前端源码
│   ├── components/     # Vue组件
│   ├── App.vue         # 主应用组件
│   └── main.js         # 入口文件
├── tests/              # 测试用例
├── utils/              # 工具函数
├── api.py              # Flask后端入口
├── package.json        # 前端依赖配置
└── vite.config.js      # Vite配置
```

---

## 安装指南 | Installation Guide

### 环境要求 | Requirements

| 组件 | 版本要求 | Component | Version |
|:---|:---|:---|:---|
| Python | 3.10+ | Python | 3.10+ |
| Node.js | 16+ | Node.js | 16+ |
| npm | 8+ | npm | 8+ |

### 安装步骤 | Installation Steps

#### 1. 克隆项目 | Clone the Repository

```bash
git clone https://github.com/yourusername/AiTeachers.git
cd AiTeachers
```

#### 2. 安装后端依赖 | Install Backend Dependencies

```bash
# 创建虚拟环境（可选但推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install flask flask-cors pyjwt chromadb
```

#### 3. 安装前端依赖 | Install Frontend Dependencies

```bash
npm install
```

---

## 使用说明 | Usage

### 启动后端服务 | Start Backend Service

```bash
python api.py
```

后端服务将在 `http://localhost:5000` 启动。

The backend service will start at `http://localhost:5000`.

### 启动前端开发服务器 | Start Frontend Development Server

```bash
npm run dev
```

前端服务将在 `http://localhost:5173` 启动。

The frontend service will start at `http://localhost:5173`.

### 构建前端生产版本 | Build Frontend for Production

```bash
npm run build
```

构建产物将生成在 `dist/` 目录。

Build output will be in the `dist/` directory.

### 登录凭证 | Login Credentials

| 用户名 | 密码 | Username | Password |
|:---|:---|:---|:---|
| admin | 123456 | admin | 123456 |

---

## API接口 | API Endpoints

### 聊天接口 | Chat Endpoint

**POST** `/chat`

请求体 | Request Body:
```json
{
  "message": "作文内容或咨询问题",
  "essay_type": "议论文/记叙文/说明文（可选）"
}
```

响应示例 | Response Example:
```json
{
  "success": true,
  "data": {
    "score": 42,
    "total_score": 50,
    "essay_type": "议论文",
    "dimensions": [
      {"name": "立意与中心", "score": 8, "max_score": 10},
      {"name": "论点与论证", "score": 9, "max_score": 10}
    ],
    "overall_comment": "文章论点明确，论证充分...",
    "improvements": ["建议增加更多实例..."]
  }
}
```

### 登录接口 | Login Endpoint

**POST** `/login`

请求体 | Request Body:
```json
{
  "username": "admin",
  "password": "123456"
}
```

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

- 邮箱 | Email: contact@aiteacher.com
- GitHub: [yourusername](https://github.com/yourusername)

---

*Made with ❤️ by AITeacher Team*
