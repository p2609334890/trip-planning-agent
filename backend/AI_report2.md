### 总体思路

你这份 `AI_report.md` 其实已经把**目标架构**画好了。你现在要做的是：先把“骨架”搭起来，再一点点往里填“肉”（模型调用、Tool、业务逻辑等）。下面给你一个从 0 开始的**实战路线图**，每一步都可以单独完成、跑通。

---

### 第 1 步：准备环境 & 基础工程

- **创建虚拟环境 + 安装依赖**
  - 在 `backend/` 下创建 venv（或用 conda）  
  - `requirements.txt` 建议至少包含：
    - **Web 框架**：`fastapi`, `uvicorn[standard]`
    - **数据模型**：`pydantic`
    - **LLM / Agent**：`langchain`, `langchain-openai`（或你要用的模型 SDK）
    - **配置 & 工具**：`python-dotenv`, `httpx` 等
- **确认 `.env`**  
  - 写好：`OPENAI_API_KEY` 或其他 LLM Key，数据库 / Redis / 第三方 API Key 等。

--- 

### 第 2 步：按架构搭基本目录骨架

先只建空文件，目的是让结构落地（不急着写逻辑）：

- `app/main.py`：创建 `FastAPI` 实例，挂载 `/api/v1` 路由。
- `app/config.py`：定义 `Settings` 类，从 `.env` 读取配置。
- `app/extensions.py` / `dependencies.py`：预留 DB、缓存、当前用户等依赖位置。
- `app/api/v1/`：
  - `trip_routes.py`：预留 `/trip/plan` 接口。
  - `health_routes.py`：`/health` 健康检查，返回 `"ok"`。
- `app/models/`：
  - `trip_request.py`：`TripPlanRequest`（目的地、日期、人数、预算、偏好等）。
  - `trip_plan.py`：`TripPlan`（按天行程、景点/酒店、预算、坐标点等）。
- `app/services/`：
  - `llm_service.py`：封装 LLM 调用（先用最简单版本，单轮调用）。
  - 其他 service 先建空壳：`attractions_service.py`, `hotels_service.py`, `weather_service.py`, `budget_service.py`, `geo_service.py`。
- `app/agents/`：
  - `workflows/trip_planning_chain.py`：预留一个函数 `run_trip_planning(request: TripPlanRequest) -> TripPlan`。
  - `prompts/trip_planning_prompt.md`：写一版初始提示词。
- `observability/logger.py`：简单封装 `logging.getLogger`。
**目标**：这个阶段结束时，项目可以 `uvicorn app.main:app --reload` 启动，`/health` 能返回 200。

---

### 第 3 步：先实现“最小可用”的 Trip 接口（不接真实外部服务）

- **建请求/响应模型**
  - 在 `trip_request.py` & `trip_plan.py` 里用 `pydantic` 定义字段，先按你前端表单需求来。


- **在 `trip_routes.py` 实现 `/trip/plan`**
  - `POST /api/v1/trip/plan`，接收 `TripPlanRequest`，返回 `TripPlan`。


- **简化版 `llm_service` + `trip_planning_chain`**
  - 先不做复杂 Tool 调用，直接：
    - 把请求参数整理成 Prompt；
    - 调用 LLM（`llm_service.generate_itinerary(prompt)`）；
    - 用一个简单规则把 LLM 文本“解析”成 `TripPlan`（哪怕是很粗糙的结构）。
- **验证链路**
  - 用 `curl` / `Postman` / `FastAPI docs` 调用 `/trip/plan`，能返回一份“看起来像行程”的 JSON 即可。

**这一步的目标**：先有一个“会说话的行程规划 Agent”，虽然不准、不连工具，但链路整体打通。

---

### 第 4 步：引入 LangChain 工具化（Tools + Services）

现在开始把架构图里的 Tool / Service 一点点接上：

- **设计服务层接口（services）**
  - 在每个 `*_service.py` 里先只定义函数签名和假数据：
    - `search_attractions(city, days, preferences) -> List[Attraction]`
    - `recommend_hotels(city, budget, location_pref) -> List[Hotel]`
    - `get_weather_forecast(city, date_range) -> WeatherInfo`
    - `estimate_budget(trip_request, attractions, hotels) -> BudgetSummary`
    - `plan_route(points) -> RouteInfo`
  - 先返回硬编码 / 假数据，保证形状对。

！！！ 使用文件较多，整合到一个文件agent.services.   封装tool文件 → agent_tool


- **创建 Tool 封装（agents/tools）**
  - 如 `attractions_tool.py` 里，用 LangChain 的 `@tool` 或 `StructuredTool` 把上面的服务函数包成 Tool。
- **在 `trip_planning_chain.py` 中组合工作流**
  - 定义一个带 Tools 的 Agent（ReAct / Tool Calling 皆可）：
    - 系统 Prompt：你的 `trip_planning_prompt.md`。
    - 可用 Tools：景点、酒店、天气、预算、地图。
  - 在 `run_trip_planning(request)` 中：
    - 把 `TripPlanRequest` 转成 Agent 的输入；
    - 调 Agent，让它按需要调用 Tools；
    - 最后把 Agent 的输出组织成 `TripPlan`。

    ！！！  langGraph实现
    # 4. 调用 Agent：按照 LangGraph Agent 的预期输入/输出结构
    state = await agent.ainvoke({"messages": [HumanMessage(content=user_input)]})
    messages = state.get("messages", [])
    final_msg = messages[-1] if messages else None
    final_text = getattr(final_msg, "content", "") if final_msg is not None else ""

**目标**：`/trip/plan` 调用时，能看到模型在日志中“调用工具”的行为（哪怕工具目前只返回假数据）。
！！！ 在终端中显示，增加日志







---

### 第 5 步：逐步替换假数据为真实能力

- **按优先级接入真实服务**
  - 通常顺序：景点 → 酒店 → 天气 → 预算 → 地图。
  - 在 `services` 中：
    - 接第三方 API（高德 / 百度 / 其他旅游 API）；
    - 或读你自己的向量库（`retrieval_service` + `vector_repository`）。
！！！ 使用GIThub的FAISS向量库  使用huggingface镜像

- **增加缓存 & 持久化**
  - `cache_repository`：缓存热门城市、常见查询结果；
  - `user_repository` / `user_context_service`：如果后面要做“用户历史行程”。
---

### 第 6 步：观测性与异常处理

- **统一日志**
  - 在 `logger.py` 配好 logger，主要接口与核心链路打印关键信息（请求参数、调用哪几个 Tool、省略敏感字段）。
- **异常处理**
  - 在 `exceptions/custom_exceptions.py` 定义业务异常；
  - `exceptions/exception_handler.py` 注册到 FastAPI，统一返回错误结构。
- **健康检查和简单监控**
  - `health_routes.py` 增加版本号、主要依赖检查；
  - 视情况增加 tracing / metrics（可后置）。

---

### 第 7 步：和前端联调 & UX 调优

- **对齐前端需求**
  - 确定 `TripPlan` 的 JSON 结构能直接被前端的地图组件、行程展示组件使用（坐标格式、时间格式等）。
- **调 Prompt 和 Tool 使用策略**
  - 为了行程更“接地气”，需要不断：
    - 调整提示词；
    - 调整 Tool 的说明（何时调用、怎么用）；
    - 限制预算、偏好等约束条件。

---

### 如果你希望一个“最小路线”

如果你想尽快跑通、少走弯路，可以按下面 4 个里程碑来做：

1. **M0：FastAPI + `/health` + 配置加载 OK**  
2. **M1：`/trip/plan` + 简单 `llm_service`，返回纯 LLM 文本行程**  
3. **M2：`/trip/plan` 内部使用 LangChain + 假数据 Tools，结构化 `TripPlan`**  
4. **M3：逐个 Tool 接入真实服务（景点 / 酒店 / 天气 / 预算 / 地图）**

---

如果你愿意，我可以下一步帮你：  
- 按你当前 `backend` 里已经有的文件，具体列出**每个文件的建议代码骨架**（类名/函数名），让你照着实现；  
- 或者先针对 “M1 最小可行版本” 给出完整的 `TripPlanRequest` / `TripPlan` 设计和 `/trip/plan` 接口伪代码。