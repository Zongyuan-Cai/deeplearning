from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    SUMMARIZE = "summarize"
    EXTRACT = "extract"
    LOCATE = "locate"
    FILL = "fill"
    UPDATE_TABLE = "update_table"
    COMPARE = "compare"
    VALIDATE = "validate"
    WRITE = "write"
    SCAN_TEMPLATE = "scan_template"


class TaskKeywordRule(BaseModel):
    task_type: TaskType
    keywords: list[str] = Field(default_factory=list)
    priority: int = 100


class TaskConfig(BaseModel):
    default_task_type: TaskType = TaskType.SUMMARIZE
    keyword_rules: list[TaskKeywordRule] = Field(default_factory=list)
    allow_fallback: bool = True

    def infer_task_type(self, user_request: str) -> TaskType:
        text = (user_request or "").strip().lower()
        if not text:
            return self.default_task_type

        best_task = self.default_task_type
        best_score = -1
        best_priority = 10**9

        for rule in self.keyword_rules:
            score = 0
            for keyword in rule.keywords:
                kw = (keyword or "").strip().lower()
                if kw and kw in text:
                    score += 1
            if score <= 0:
                continue

            if score > best_score or (score == best_score and rule.priority < best_priority):
                best_task = rule.task_type
                best_score = score
                best_priority = rule.priority

        return best_task


DEFAULT_TASK_CONFIG = TaskConfig(
    default_task_type=TaskType.SUMMARIZE,
    keyword_rules=[
        TaskKeywordRule(task_type=TaskType.SUMMARIZE, keywords=["总结", "概括", "归纳", "摘要", "summarize"], priority=100),
        TaskKeywordRule(task_type=TaskType.EXTRACT, keywords=["提取", "抽取", "找出", "识别", "extract"], priority=90),
        TaskKeywordRule(task_type=TaskType.FILL, keywords=["填写", "填入", "填表", "回填", "fill"], priority=80),
        TaskKeywordRule(task_type=TaskType.LOCATE, keywords=["定位", "查找", "找到", "locate"], priority=80),
        TaskKeywordRule(task_type=TaskType.COMPARE, keywords=["比较", "对比", "compare"], priority=70),
        TaskKeywordRule(task_type=TaskType.VALIDATE, keywords=["校验", "验证", "检查", "validate"], priority=70),
        TaskKeywordRule(task_type=TaskType.SCAN_TEMPLATE, keywords=["模板", "扫描模板", "scan template"], priority=75),
        TaskKeywordRule(task_type=TaskType.WRITE, keywords=["写入", "输出", "write"], priority=85),
    ],
    allow_fallback=True,
)


def infer_task_type(user_request: str, config: TaskConfig | None = None) -> str:
    cfg = config or DEFAULT_TASK_CONFIG
    return cfg.infer_task_type(user_request).value


# 兼容旧常量
TASK_KEYWORDS = {rule.task_type.value: list(rule.keywords) for rule in DEFAULT_TASK_CONFIG.keyword_rules}
DEFAULT_TASK_TYPE = DEFAULT_TASK_CONFIG.default_task_type.value
