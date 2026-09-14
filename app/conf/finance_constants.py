"""金融知识库业务常量：集中管理实体类型、问题类型、合规禁用词等"""

# 内容类型（写入 chunk 元数据 content_type）
CONTENT_TYPES = ["产品说明书", "风险提示", "公告摘要", "FAQ", "金融术语", "市场资讯", "业务流程"]

# 问题类型（写入 state.question_type）
QUESTION_ENTITY = "实体型"      # 有明确产品/公司
QUESTION_CONCEPT = "概念型"     # 什么是 XX
QUESTION_RISK = "风险型"        # 会亏钱吗 / 风险多大
QUESTION_BUSINESS = "业务型"    # 如何赎回 / 多久到账

# 合规禁用词（用于答案后置校验 / 提示词负向约束）
FORBIDDEN_PHRASES = [
    "一定赚钱", "保证收益", "保本无风险", "稳赚不赔", "一定上涨", "现在必须买入",
    "稳赚", "包赚", "绝无风险",
]

# 无资料时的固定兜底话术（必须与 answer_out.prompt 保持一致）
NO_DATA_ANSWER = (
    "当前知识库中未检索到足够信息，建议查看正式产品文件、公告原文或咨询相关工作人员。"
)

# 实体对齐阈值（沿用掌柜智库）
ENTITY_HIGH_SCORE = 0.85     # >= 直接确认
ENTITY_MIDDLE_SCORE = 0.60   # 0.6~0.85 反问用户