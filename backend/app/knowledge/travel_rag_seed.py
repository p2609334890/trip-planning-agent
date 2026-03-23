"""
旅行领域 RAG 静态知识片段：写入向量库后供 hybrid_search 语义召回。
内容偏常识与规划提示，非实时票价/开放时间；规划时须与高德/MCP 等实时数据对照。
"""

from typing import Any

# 每条对应一次 store_destination_knowledge(destination, knowledge_data)
DESTINATION_KNOWLEDGE_SEED: list[tuple[str, dict[str, Any]]] = [
    (
        "北京",
        {
            "description": "首都历史文化厚重，核心区地铁覆盖好；热门场馆多实行预约制。",
            "highlights": ["故宫与国博需提前预约", "长城慕田峪相对人少", "胡同与四合院体验京味"],
            "best_season": "春秋气候宜人；夏季闷热、冬季干冷需注意保暖。",
            "culture": "中轴线、皇家园林与民俗并存；用餐可尝试烤鸭、涮肉与小吃街。",
        },
    ),
    (
        "上海",
        {
            "description": "国际化大都市，浦江两岸夜景与租界历史建筑是经典组合。",
            "highlights": ["外滩-陆家嘴天际线", "豫园与老城厢", "迪士尼需预留整日"],
            "best_season": "春秋舒适；梅雨季与盛夏湿热需备雨具与透气衣物。",
            "culture": "海派文化；本帮菜偏甜鲜，咖啡与西餐选择丰富。",
        },
    ),
    (
        "杭州",
        {
            "description": "西湖为核心，适合慢行与环湖公交；灵隐、西溪湿地可分散客流。",
            "highlights": ["西湖十景与游船", "灵隐寺香火旺宜早到", "龙井村茶文化"],
            "best_season": "春季与秋季最佳；节假日断桥苏堤拥挤可改走杨公堤。",
            "culture": "南宋遗韵与江南园林；杭帮菜清淡，绿茶与点心出名。",
        },
    ),
    (
        "成都",
        {
            "description": "休闲与美食之都，川西门户；市区与近郊景点可拆分多日。",
            "highlights": ["大熊猫基地宜上午", "宽窄巷子与锦里夜景", "火锅与串串"],
            "best_season": "全年可游；夏季闷热、冬季多雾，盆地气候湿润。",
            "culture": "巴蜀文化与茶馆慢生活；辣度可向店家说明微调。",
        },
    ),
    (
        "西安",
        {
            "description": "十三朝古都，兵马俑与城墙是标志；陕历博等需预约。",
            "highlights": ["兵马俑建议讲解", "城墙骑行日落段", "回民街小吃集中"],
            "best_season": "春秋最佳；夏季炎热、冬季干冷。",
            "culture": "汉唐遗迹与丝路记忆；面食与羊肉泡馍是日常味型。",
        },
    ),
]

# 每条对应一次 store_travel_experience(experience_type, experience_data)
EXPERIENCE_KNOWLEDGE_SEED: list[tuple[str, dict[str, Any]]] = [
    (
        "行程节奏",
        {
            "title": "多日城市游节奏",
            "description": "每天主景点不超过2到3个，预留交通与用餐缓冲；把体力消耗大的项目放在上午。",
            "tags": ["节奏", "体力", "缓冲时间"],
            "destination": "通用",
        },
    ),
    (
        "预算与预订",
        {
            "title": "机酒与门票",
            "description": "机票酒店提前预订通常更稳；热门博物馆与演艺票建议官方渠道预约，警惕非正规代购。",
            "tags": ["预算", "预订", "防骗"],
            "destination": "通用",
        },
    ),
    (
        "亲子与老人",
        {
            "title": "家庭出行",
            "description": "老人与儿童减少换酒店次数；景点间距离控制在合理范围，备常用药与便携零食。",
            "tags": ["亲子", "老人", "安全"],
            "destination": "通用",
        },
    ),
    (
        "高原与山区",
        {
            "title": "高海拔注意事项",
            "description": "进入高原首日避免剧烈运动，注意保暖与补水；出现持续头痛、呕吐应下撤并就医。",
            "tags": ["高原反应", "安全", "健康"],
            "destination": "川西滇西北等",
        },
    ),
    (
        "交通接驳",
        {
            "title": "枢纽到市区",
            "description": "大型机场/高铁站预留出站与安检时间；优先地铁与正规网约车，记下酒店地址与紧急联系人。",
            "tags": ["交通", "接驳", "安全"],
            "destination": "通用",
        },
    ),
]
