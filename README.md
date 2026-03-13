# 🧳 MyTrip — 智能旅行规划助手

> 基于单智能体 + 向量记忆的一站式旅行行程生成与管理平台

## 项目简介

本项目面向**旅行信息分散、规划耗时、个性化不足**的痛点，提供从需求输入到完整行程生成、保存、编辑与导出的一体化解决方案。

核心特点：
<del>- **多智能体协作架构** — 景点检索、酒店推荐、天气查询、行程编排由不同智能体分工执行，整体采用 Plan-and-Solve 编
排范式，单体执行支持类 ReAct 工具调用循环</del>

- **单智能体架构** — 由一个 TripPlannerAgent 统一调度景点检索、酒店推荐、天气查询等后端服务获取真实数据，再结合对话记忆与向量记忆生成完整行程，架构简洁且稳定
- **MCP 工具链集成** — 通过 MCP 协议接入彩云天气等外部能力，结合高德地图 WebService API 获取 POI、天气与地理信息
- **向量记忆系统** — 基于 FAISS + Sentence-Transformers 实现用户偏好记忆、历史行程召回与目的地知识检索，支持个性化规划
- **Redis 持久化** — 用户数据、行程版本、访客会话均通过 Redis 持久存储，支持行程 CRUD 与列表管理
- **前后端分离** — 前端支持地图可视化、行程编辑、预算统计、PDF/图片导出等交互能力


适用场景：

- 想快速生成旅游计划的个人用户
- 需要保存、修改和管理多个行程的旅行规划场景
- 多智能体、MCP 工具调用、向量记忆相关的课程作业或实践项目

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 智能行程生成 | 根据目的地、日期、预算、偏好自动生成结构化多日行程（含景点、酒店、餐饮、预算拆分） |
| 多智能体协作规划 | 景点 Agent、酒店 Agent、天气 Agent 分别获取真实数据，规划 Agent 汇总生成最终方案 |
| 向量记忆与个性化 | FAISS 向量库记录用户偏好与历史行程，规划时通过语义检索自动召回，提升个性化推荐效果 |
| 行程持久化管理 | Redis 存储用户行程，支持创建、查看、删除；JWT + 访客双模式认证 |
| 地图可视化 | 高德地图 JS API 标注景点位置、绘制游览路线、自适应视野 |
| 行程编辑 | 支持添加/删除天数、增减景点与活动、编辑酒店信息，实时更新预算 |
| 导出功能 | 支持将行程导出为 PDF 文档或 PNG 图片 |
| 用户系统 | 注册/登录、个人资料管理（头像、旅行偏好等）、密码修改 |

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                         │
│  Home · Result · EditPlan · MyTrips · Login · Profile           │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐   │
│  │ MapView  │  │ Budget   │  │  Export   │  │  LoadingProg │   │
│  │(高德地图) │  │ Summary  │  │  Buttons  │  │   ress       │   │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ Axios (REST API)
┌────────────────────────────▼────────────────────────────────────┐
│                     Backend (FastAPI)                            │
│                                                                 │
│  ┌─ Middleware ──────────────────────────────────────────────┐   │
│  │  RequestID · JWT Auth · RateLimit · CircuitBreaker        │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ API v1 ──────────────────────────────────────────────────┐   │
│  │  /trips/plan · /trips/list · /auth/login · /auth/register │   │
│  └──────────────────────────┬────────────────────────────────┘   │
│                             │                                   │
│  ┌─ Agent Layer ────────────▼────────────────────────────────┐   │
│  │                  TripPlannerAgent                          │   │
│  │  ┌────────────┐  ┌───────────┐  ┌────────────────────┐    │   │
│  │  │ Attraction │  │  Weather  │  │   Hotel Service    │    │   │
│  │  │  Service   │  │  Service  │  │                    │    │   │
│  │  │ (高德 API) │  │ (MCP 天气)│  │   (高德 API)       │    │   │
│  │  └────────────┘  └───────────┘  └────────────────────┘    │   │
│  │         ↓ 真实数据注入 prompt                               │   │
│  │  ┌──────────────────────────────────────────────────┐      │   │
│  │  │  LLM (ChatOpenAI, GPT-4.1-mini)                 │      │   │
│  │  │  + RunnableWithMessageHistory (对话记忆)          │      │   │
│  │  │  + VectorMemoryService (向量记忆)                 │      │   │
│  │  └──────────────────────────────────────────────────┘      │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Data Layer ──────────────────────────────────────────────┐   │
│  │  Redis (用户/行程/会话)  ·  FAISS (向量索引)  ·  Pexels   │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**数据流：** 用户提交规划请求 → 后端并行调用高德/MCP获取真实景点、天气、酒店数据 → 向量记忆检索用户历史偏好 → 所有数据注入 LLM prompt 生成 JSON 行程 → 解析为强类型模型 → Pexels 补充景点图片 → 行程写入 Redis + 向量记忆 → 返回前端渲染

## 🛠️ 技术栈

### 智能体与 AI

| 组件 | 说明 |
|------|------|
| LangChain + LangChain-OpenAI | Agent 编排、Prompt 模板、对话历史管理 |
| LangGraph | 工作流编排支持 |
| ChatOpenAI (GPT-4.1-mini) | 行程生成核心 LLM（可配置 OpenAI / ModelScope / 其他兼容服务） |
| FAISS + Sentence-Transformers | 向量记忆索引，嵌入模型 paraphrase-multilingual-MiniLM-L12-v2 (384维) |

### 工具与 API

| 工具 | 用途 |
|------|------|
| MCP 天气工具 (彩云天气) | 通过 HuggingFace MCPClient 调用，支持 stdio/http/sse 三种模式 |
| 高德地图 WebService API | POI 景点搜索、酒店搜索、地理编码 |
| Pexels API | 景点图片搜索与补充 |
| 高德地图 JS API | 前端地图可视化、路线绘制 |

### 后端

| 技术 | 用途 |
|------|------|
| FastAPI + Uvicorn | ASGI Web 框架 + 服务器 |
| Redis | 用户数据、行程数据持久化（Hash + Sorted Set） |
| PyJWT + bcrypt | JWT 令牌认证 + 密码加密 |
| pydantic / pydantic-settings | 数据校验 + 类型安全配置管理 |

### 前端

| 技术 | 用途 |
|------|------|
| Vue 3 (Composition API) + TypeScript | UI 框架 |
| Vite 6 | 开发/构建工具 |
| Element Plus + Tailwind CSS 4 | UI 组件库 + 原子化样式 |
| Pinia | 状态管理（认证状态） |
| Vue Router 4 | 路由管理（History 模式 + 路由守卫） |
| Axios | HTTP 客户端（自动注入 Token、401 拦截） |
| html2canvas + jsPDF | 行程导出 PDF / 图片 |
| Day.js | 日期处理 |

## 📁 项目结构

```
mytrip/
├── README.md
├── .gitignore
├── backend/
│   ├── run.py                            # 启动入口 (uvicorn)
│   ├── requirements.txt                  # Python 依赖
│   ├── .env                              # 环境变量 (不提交)
│   └── app/
│       ├── main.py                       # FastAPI 应用工厂
│       ├── config.py                     # pydantic-settings 配置
│       ├── agents/
│       │   ├── tools/
│       │   │   └── agent_tool.py         # LangChain @tool 定义
│       │   └── workflows/
│       │       ├── trip_planning_chain.py # 行程规划入口
│       │       └── specialized_agents.py # TripPlannerAgent 核心实现
│       ├── api/v1/
│       │   ├── trip_routes.py            # 行程 CRUD API
│       │   ├── auth_routes.py            # 认证 API (登录/注册/改密)
│       │   ├── user_routes.py            # 用户路由
│       │   └── health_routes.py          # 健康检查
│       ├── middleware/
│       │   ├── auth.py                   # JWT + 访客认证
│       │   ├── rate_limit.py             # 滑动窗口限流
│       │   ├── request_id.py             # 请求 ID 追踪
│       │   ├── circuit_breaker.py        # 熔断器
│       │   └── degradation.py            # 降级策略
│       ├── models/
│       │   ├── common.py                 # Location, Attraction, Hotel 等
│       │   ├── trip_request.py           # TripPlanRequest/Response
│       │   └── trip_plan.py              # 备用数据模型
│       ├── services/
│       │   ├── agent_sercvice.py         # 景点/酒店/天气/预算核心业务
│       │   ├── redis_service.py          # Redis 持久化
│       │   ├── retrieval_service.py      # FAISS 向量记忆 (单例)
│       │   ├── context_manager.py        # Agent 间上下文共享
│       │   ├── local_attractions_data.py # 本地兜底景点数据
│       │   └── local_hotels_data.py      # 本地兜底酒店数据
│       ├── repositories/
│       │   ├── cache_repository.py       # 缓存仓库
│       │   ├── user_repository.py        # 用户仓库
│       │   └── vector_repository.py      # 向量仓库
│       ├── exceptions/
│       │   ├── error_codes.py            # 统一错误码 (5大类)
│       │   ├── custom_exceptions.py      # 自定义异常
│       │   └── exception_handler.py      # 全局异常处理器
│       └── observability/
│           ├── logger.py                 # 结构化日志 (JSON+可读双输出)
│           └── tracing.py                # 分布式追踪 (占位)
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.ts                       # 应用入口
│       ├── App.vue                       # 根组件 (导航栏+路由)
│       ├── router/index.ts              # 路由配置 (6个页面+守卫)
│       ├── stores/auth.ts               # Pinia 认证状态
│       ├── services/api.ts              # Axios 封装 (拦截器)
│       ├── types/index.ts               # TypeScript 接口定义
│       ├── views/
│       │   ├── Home.vue                  # 首页 (规划表单)
│       │   ├── Result.vue                # 结果展示页
│       │   ├── EditPlan.vue              # 行程编辑页
│       │   ├── MyTrips.vue               # 我的行程列表
│       │   ├── Login.vue                 # 登录/注册页
│       │   └── Profile.vue               # 个人资料页
│       └── components/
│           ├── MapView.vue               # 高德地图组件
│           ├── BudgetSummary.vue         # 预算摘要
│           ├── ExportButtons.vue         # PDF/图片导出
│           ├── UserInfo.vue              # 用户信息
│           └── LoadingProgress.vue       # 加载进度
```

## 🚀 快速开始

### 前置要求

- Python 3.12+
- Node.js 18+
- Redis 服务（本地或远程）
- 高德地图 API Key（[申请地址](https://console.amap.com/)）
- OpenAI 兼容 LLM API Key

### 1. 克隆项目

```bash
git clone <repo-url>
cd mytrip
```

### 2. 后端启动

```bash
cd backend

# 创建并激活虚拟环境
python -m venv mytrip
# Windows
mytrip\Scripts\activate
# macOS/Linux
source mytrip/bin/activate

# 安装依赖
pip install -r requirements.txt
```

配置 `.env` 文件（参考以下模板）：

```env
# LLM 配置（必填）
LLM_MODEL_ID=gpt-4.1-mini
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1

# 高德地图（必填）
AMAP_API_KEY=your-amap-key

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# JWT
JWT_SECRET=your-secret-key

# MCP 天气
CAIYUN_API_KEY=your-caiyun-key
TRAVEL_MCP_SERVER_TYPE=stdio

# 图片服务（可选）
PEXELS_API_KEY=your-pexels-key

# HuggingFace 镜像（国内推荐）
HF_ENDPOINT=https://hf-mirror.com
```

启动后端服务：

```bash
python run.py
```

服务默认运行在 `http://localhost:8000`

### 3. 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
# 创建 .env.local
# VITE_API_BASE_URL=http://localhost:8000
# VITE_AMAP_KEY=your-amap-js-key

# 开发模式启动
npm run dev
```

访问 `http://localhost:5173` 即可使用。

## 📡 API 接口概览

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/trips/plan` | 生成智能行程 |
| `GET` | `/api/v1/trips/list` | 获取用户行程列表 |
| `GET` | `/api/v1/trips/{trip_id}` | 获取行程详情 |
| `DELETE` | `/api/v1/trips/{trip_id}` | 删除行程 |
| `POST` | `/api/v1/auth/login` | 用户登录 |
| `POST` | `/api/v1/auth/register` | 用户注册 |
| `PUT` | `/api/v1/auth/password` | 修改密码 |
| `GET` | `/health` | 健康检查 |

## 🔧 设计亮点

**数据先行，LLM 后编排**
后端先并行调用高德/MCP 拿到真实景点、天气、酒店数据，再将结构化数据注入 LLM prompt，避免 LLM 直接调工具带来的不稳定性，同时保证行程中的地址、价格等信息可靠。

**向量记忆闭环**
每次规划完成后，自动将行程和偏好写入 FAISS 向量库；下次规划时通过语义检索召回用户历史偏好与目的地知识，形成"规划→记忆→检索→优化"的闭环，持续提升个性化体验。

**地理位置验证**
规划 Agent 的 system prompt 强制要求验证景点经纬度是否在目标城市范围内，同一天景点距离不超过 50km，相邻天主要景点距离不超过 100km，避免跨区域不合理的行程编排。

**本地兜底数据**
当高德 API 不可用时，系统自动回退到内置的热门城市景点/酒店数据，确保基础功能可用。

**工程化中间件**
内置请求 ID 追踪、滑动窗口限流（全局 100/s，IP 20/s）、熔断器、降级策略，以及 JSON + 人类可读双格式的结构化日志。

## 📄 许可证

MIT
