## 整体架构分层（FastAPI + LangChain）

先用文字“画”一下整体模块关系，方便你脑中成图：

- **用户交互层（前端）**  
  - Vue / React 前端，通过 FastAPI 提供的 REST API / WebSocket，与智能行程规划后端交互。  
  - 负责展示：行程日历、景点/酒店列表、预算明细、交互式地图可视化（高德/百度/Mapbox 等）。

- **API 层（FastAPI 路由）**  
  - 提供统一版本化接口：如 `/api/v1/trip/plan`、`/api/v1/trip/budget`、`/api/v1/trip/map` 等。  
  - 使用 FastAPI 的依赖注入机制做参数校验、鉴权、限流等横切逻辑。  
  - 调用“智能体编排层”的接口获取行程规划结果、预算计算结果、地图坐标与路线等。  
  - 统一返回 JSON / 错误格式，并由 FastAPI 自动生成 OpenAPI/Swagger 文档，便于前后端联调。

- **智能体编排层（LangChain）**  
  - **主规划链 / 工作流**：负责根据用户输入的目的地、出行日期、人数、预算范围、出行偏好（亲子/美食/小众/博物馆等），组织各个子 Agent / 工具，生成完整行程。  
  - **子 Agent / 工具**（LangChain Tools / 自定义函数）：  
    - 景点推荐 Agent / Tool（按主题、距离、评分、开放时间筛选景点）  
    - 酒店推荐 Agent / Tool（按预算、地理位置、评分、交通便利性等推荐住宿）  
    - 天气查询 Tool（按城市+日期范围调用天气 API，给出天气趋势与提醒）  
    - 预算计算 Tool（根据机票/酒店/门票/交通/餐饮等估算总预算及每日预算）  
    - 地图与路线规划 Tool（调用高德/百度/Mapbox 等 API，生成经纬度坐标与步行/地铁/自驾路线）  
  - 使用 LangChain 的 RouterChain / Multi-Tool Agent 等机制，按需调用不同工具，支持错误重试、工具退避、上下文记忆等。  
  - 如后续需要更复杂的有向图编排，可进一步演进到 LangGraph 实现可视化工作流。

- **领域服务层（Python Service）**  
  - 纯 Python 业务逻辑层，LangChain 的 Tool 大多通过这里访问外部服务：  
    - LLM 调用服务（统一 OpenAI / DeepSeek / 其他厂商的模型，支持多模型切换与重试策略）  
    - 向量检索服务（FAISS / Chroma，用于检索本地旅行攻略/游记知识库）  
    - 地理 & 地图服务（高德/百度 API 封装：POI 搜索、路线规划、坐标转换）  
    - 天气服务（查询未来若干天的天气预报、气温、降水概率，给出穿衣/备用方案建议）  
    - 汇率与预算服务（按汇率换算不同币种消费，支持人均预算与总预算估算）。

- **数据访问层**  
  - 向量库封装（检索、索引构建），支撑对“本地旅行知识库”的语义搜索。  
  - Redis 缓存（热门景点、热门城市、常见查询结果、用户会话上下文），减少第三方 API 调用次数。  
  - 业务数据库/文件系统（持久化用户行程方案、收藏的景点/酒店、用户偏好与历史记录）。

- **基础设施层**  
  - 配置管理（多环境配置、API Key 管理、.env 加载）。  
  - 日志与链路追踪（记录每次行程规划的关键步骤，便于排查问题与优化 Prompt）。  
  - 异常处理与监控（统一错误格式、慢请求监控、外部 API 可用性监控）。  
  - 中间件（CORS、请求限流、请求 ID、用户鉴权等）。

---

## 后端目录结构示意（FastAPI + LangChain）

假设现在的后端目录为 `backend/`，可以演进成类似下面这样（只列关键部分）：

```bash
backend/
  app/
    main.py                # FastAPI 应用入口：创建 app、挂载路由、中间件
    config.py              # 配置类（Dev/Prod），读取 .env
    dependencies.py        # 依赖注入：DB 会话、缓存客户端、当前用户、节流器等

    api/
      __init__.py          # 注册路由前缀与 APIRouter
      v1/
        __init__.py
        trip_routes.py     # /api/v1/trip/* 行程相关接口（生成行程、获取预算、导出行程）
        health_routes.py   # 健康检查、版本信息等
        user_routes.py     #（如有）用户偏好、登录/鉴权相关

    agents/                # LangChain 智能体与工作流
      __init__.py
      base/
        agent_base.py      # 通用 Agent 封装（带 Memory、Tools 的 ReAct/Tool Agent）
      tools/
        attractions_tool.py  # 景点推荐 Tool（封装调用 attractions_service）
        hotels_tool.py       # 酒店推荐 Tool
        weather_tool.py      # 天气查询 Tool
        budget_tool.py       # 预算估算 Tool
        geo_tool.py          # 地理/路线 Tool（高德/百度/Mapbox）
      workflows/
        trip_planning_chain.py  # 使用 LangChain 组合各 Tool 的主工作流
      prompts/
        trip_planning_prompt.md  # 行程规划系统/角色提示词
        tool_prompts.md          # 各 Tool 的说明/约束提示词

    services/              # 领域服务（被 Tools/Agents 调用）
      __init__.py
      llm_service.py       # 封装 LangChain LLM / ChatModel 调用，统一模型 & 重试
      retrieval_service.py # 向量检索：封装 FAISS/Chroma（加载索引、查询）
      attractions_service.py # 景点搜索业务逻辑（可调第三方 API 或自建数据）
      hotels_service.py      # 酒店推荐逻辑
      weather_service.py     # 天气查询（第三方 API 封装）
      geo_service.py         # 地图：POI、路线、坐标转换、静态图/前端渲染参数
      budget_service.py      # 成本估算逻辑（机酒+门票+交通+餐饮）
      user_context_service.py# 用户偏好、历史行程上下文

    models/                # Pydantic 数据模型（请求/响应/领域对象）
      __init__.py
      trip_request.py      # 行程请求模型：目的地、时间、预算、偏好等
      trip_plan.py         # 行程规划结果：按天行程、景点/酒店列表、预算汇总、地图点位等
      common.py            # 通用响应模型、分页等

    repositories/          # 数据持久层封装
      __init__.py
      vector_repository.py # 操作向量库（建索引、保存、搜索）
      cache_repository.py  # 操作 Redis（缓存热门城市、查询结果等）
      user_repository.py   #（如有）用户数据持久化

    observability/
      __init__.py
      logger.py            # 日志封装
      tracing.py           #（可选）链路追踪/指标上报

    exceptions/
      __init__.py
      custom_exceptions.py   # 业务异常定义
      exception_handler.py   # FastAPI 全局异常处理，统一返回格式

  start_dev.sh / start_dev.ps1 # 开发环境启动脚本，内部使用 uvicorn
  requirements.txt             # 包含 fastapi + uvicorn + langchain + 各服务 SDK 等
```

---

## 模块协作示例（请求流：生成智能行程）

以核心接口 `/api/v1/trip/plan` 为例的大致调用链（覆盖景点推荐、酒店推荐、天气查询、预算计算、地图可视化等功能）：

1. **前端**  
   - 用户在页面输入：目的地（可以是多个城市）、出行日期范围、人数、总体预算/人均预算、出行偏好等。  
   - 前端将这些参数封装为 `TripPlanRequest`，通过 POST 请求调用 `/api/v1/trip/plan`。  
2. **FastAPI 路由（`trip_routes.py`）**  
   - 使用 Pydantic 自动校验请求体 → 构造 `TripPlanRequest` 模型。  
   - 注入所需依赖（如 `llm_service`、`attractions_service` 等）。  
   - 调用 `trip_planning_chain.run(request)`（`agents/workflows/trip_planning_chain.py`）。  
3. **LangChain 工作流（`trip_planning_chain`）**  
   - 根据用户偏好，决定行程天数与每日节奏（密集/休闲）。  
   - 并行或按步骤调用各 Tool：  
     - 景点推荐 Tool → `attractions_service`：检索本地知识库 + 第三方 API，生成候选景点列表。  
     - 酒店推荐 Tool → `hotels_service`：结合预算与地理位置，推荐酒店备选。  
     - 天气查询 Tool → `weather_service`：获取未来天气，为某些活动给出备选方案。  
     - 预算计算 Tool → `budget_service`：估算机酒+门票+交通+餐饮的整体预算，并按天拆分。  
     - 地图 Tool → `geo_service`：返回各景点/酒店的经纬度坐标与大致路线规划参数。  
   - 调用 LLM（`llm_service`）对上述工具输出进行综合推理与润色，生成“按天行程 + 文字说明 + 小贴士”。  
4. **服务层 & 仓储层**  
   - 需要时查询向量库（用户过往行程/本地攻略）、Redis 缓存（热门景点、历史查询结果）、外部 API（地图、天气、酒店）。  
   - 可将本次生成的行程方案与用户偏好写入数据库，便于后续查看与二次编辑。  
5. **返回**  
   - 工作流返回标准 `TripPlan` 模型，包括：  
     - 每日行程列表、时间节点、对应景点/酒店信息  
     - 预算汇总与分项预算  
     - 地图可视化所需的坐标点与路线参数  
   - FastAPI 将其序列化为 JSON，前端根据坐标在地图组件中渲染线路与打点，并展示预算与文字说明。

