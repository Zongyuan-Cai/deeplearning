from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TargetStrategy(str, Enum):
    AUTO = "auto"
    BY_LABEL = "by_label"
    BY_NEARBY_TEXT = "by_nearby_text"
    BY_TABLE_COORD = "by_table_coord"
    BY_STRUCTURE_RULE = "by_structure_rule"


class NearbyTextSelector(BaseModel):
    anchor_text: str
    window: int = 1
    direction: str = "both"  # before / after / both
    case_sensitive: bool = False


class TableCoordinateSelector(BaseModel):
    table_index: int
    row_index: int
    col_index: int


class StructureRuleSelector(BaseModel):
    scope: str = "paragraph"  # paragraph / table_cell
    style_contains: str | None = None
    heading_level: int | None = None
    section_path_contains: list[str] = Field(default_factory=list)
    table_header_contains: list[str] = Field(default_factory=list)


class TargetSelector(BaseModel):
    strategy: TargetStrategy = TargetStrategy.AUTO
    hint: str = ""

    # 按标签找
    label: str | None = None
    label_aliases: list[str] = Field(default_factory=list)
    exact_match: bool = True
    fuzzy_match_threshold: float = 0.6

    # 按邻近文本找
    nearby: NearbyTextSelector | None = None

    # 按表格坐标找
    table_coordinate: TableCoordinateSelector | None = None

    # 按结构规则找
    structure_rule: StructureRuleSelector | None = None

    # 失败降级策略
    fallback_strategies: list[TargetStrategy] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def normalized(self) -> "TargetSelector":
        fallback = list(self.fallback_strategies)
        if self.strategy == TargetStrategy.AUTO and not fallback:
            fallback = [
                TargetStrategy.BY_LABEL,
                TargetStrategy.BY_NEARBY_TEXT,
                TargetStrategy.BY_TABLE_COORD,
                TargetStrategy.BY_STRUCTURE_RULE,
            ]
        return self.model_copy(update={"fallback_strategies": fallback})

    def to_locator_params(self) -> dict[str, Any]:
        selector = self.normalized()
        payload: dict[str, Any] = {
            "target_strategy": selector.strategy.value,
            "target_hint": selector.hint,
            "fallback_strategies": [x.value for x in selector.fallback_strategies],
        }

        if selector.label:
            payload["field_name"] = selector.label
            payload["label_aliases"] = selector.label_aliases
            payload["exact_match"] = selector.exact_match
            payload["fuzzy_match_threshold"] = selector.fuzzy_match_threshold

        if selector.nearby:
            payload["near_keyword"] = selector.nearby.anchor_text
            payload["nearby_window"] = selector.nearby.window
            payload["case_sensitive"] = selector.nearby.case_sensitive

        if selector.table_coordinate:
            payload["table_cell"] = selector.table_coordinate.model_dump()

        if selector.structure_rule:
            payload["structure_rule"] = selector.structure_rule.model_dump()

        if selector.metadata:
            payload["selector_metadata"] = dict(selector.metadata)

        return payload


def build_target_selector(payload: dict[str, Any] | None = None) -> TargetSelector:
    data = payload if isinstance(payload, dict) else {}
    if not data:
        return TargetSelector()

    strategy = data.get("strategy")
    if isinstance(strategy, str):
        normalized_strategy = strategy.strip().lower().replace("-", "_")
        alias = {
            "label": TargetStrategy.BY_LABEL,
            "nearby": TargetStrategy.BY_NEARBY_TEXT,
            "table_coord": TargetStrategy.BY_TABLE_COORD,
            "coord": TargetStrategy.BY_TABLE_COORD,
            "structure": TargetStrategy.BY_STRUCTURE_RULE,
        }.get(normalized_strategy)
        if alias is not None:
            data = dict(data)
            data["strategy"] = alias.value

    return TargetSelector.model_validate(data)
