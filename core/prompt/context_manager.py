from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol
import json
import re


BlockKind = Literal["fixed", "variable"]


class TruncationStrategy(Protocol):
    """截断策略接口：输入原始 payload，输出截断后的 payload。"""

    def __call__(self, payload: Any, *, budget_chars: int, **kwargs: Any) -> Any: ...


@dataclass
class ContextBlock:
    """一个参与上下文预算的块，可以是固定块或可截断块。"""

    name: str
    kind: BlockKind
    payload: Any
    truncatable: bool = False
    priority: int = 1
    strategy_name: Optional[str] = None
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    estimated_chars: int = 0

    @staticmethod
    def fixed(name: str, payload: str, priority: int = 10) -> "ContextBlock":
        return ContextBlock(
            name=name,
            kind="fixed",
            payload=payload,
            truncatable=False,
            priority=priority,
        )

    @staticmethod
    def variable(
        name: str,
        payload: Any,
        *,
        strategy_name: str,
        priority: int = 5,
        truncatable: bool = True,
        **strategy_params: Any,
    ) -> "ContextBlock":
        return ContextBlock(
            name=name,
            kind="variable",
            payload=payload,
            truncatable=truncatable,
            priority=priority,
            strategy_name=strategy_name,
            strategy_params=strategy_params or {},
        )


def estimate_chars(obj: Any) -> int:
    """粗略估算一个对象转成文本后的字符数。"""
    if obj is None:
        return 0
    if isinstance(obj, str):
        return len(obj)
    try:
        text = json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(obj)
    return len(text)


_DATA_KEYWORDS = [
    "营收",
    "收入",
    "营收增长",
    "利润",
    "净利",
    "毛利",
    "亏损",
    "同比",
    "环比",
    "增长率",
    "下滑",
    "增速",
    "市场份额",
    "份额",
    "出货量",
    "销量",
    "估值",
    "市值",
    "融资",
    "募资",
    "订单",
    "预订量",
    "装机量",
    "渗透率",
    "revenue",
    "profit",
    "margin",
    "gross margin",
    "net income",
    "loss",
    "guidance",
    "forecast",
    "projection",
    "outlook",
    "market share",
    "volume",
    "shipment",
    "capex",
    "opex",
    "valuation",
]

_TECH_KEYWORDS = [
    "架构",
    "工艺",
    "制程",
    "算力",
    "带宽",
    "延迟",
    "吞吐",
    "性能",
    "峰值性能",
    "能效比",
    "功耗",
    "芯片",
    "GPU",
    "CPU",
    "NPU",
    "加速卡",
    "加速器",
    "数据中心",
    "推理",
    "训练",
    "推理性能",
    "内存带宽",
    "高带宽内存",
    "HBM",
    "CoWoS",
    "architecture",
    "throughput",
    "latency",
    "bandwidth",
    "power consumption",
    "efficiency",
    "accelerator",
    "data center",
    "inference",
    "training",
    "benchmark",
    "node",
    "3nm",
    "5nm",
]

_ANALYSIS_KEYWORDS = [
    "我们认为",
    "我们预计",
    "我们判断",
    "在我们看来",
    "这意味着",
    "这表明",
    "这可能导致",
    "核心观点",
    "关键结论",
    "综合来看",
    "总体来看",
    "预计将",
    "有望",
    "we believe",
    "we expect",
    "in our view",
    "we think",
    "this suggests",
    "this indicates",
    "we estimate",
    "we forecast",
    "we view",
    "we see",
]


def _select_representative_paragraphs(content: str, budget_chars: int = 1800) -> str:
    """单篇文章的结构化段落截断。"""
    if not content:
        return ""

    text = content.strip()
    if len(text) <= budget_chars:
        return text

    text = re.sub(r"\n{3,}", "\n\n", text)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) < 3:
        return text[:budget_chars]

    def classify_paragraph(p: str, idx: int, total: int) -> Dict[str, Any]:
        flags: set[str] = set()

        if idx <= 1:
            flags.add("intro")
        if idx >= total - 2:
            flags.add("conclusion")

        if re.search(r"\d", p) or "%" in p:
            flags.add("data")

        lower = p.lower()
        if any(kw.lower() in lower for kw in _DATA_KEYWORDS):
            flags.add("data")
        if any(kw.lower() in lower for kw in _TECH_KEYWORDS):
            flags.add("data")
        if any(kw.lower() in lower for kw in _ANALYSIS_KEYWORDS):
            flags.add("analysis")

        weight_table = {
            "data": 5,
            "analysis": 4,
            "conclusion": 3,
            "intro": 2,
        }

        base_weight = 0
        for f in flags:
            base_weight = max(base_weight, weight_table.get(f, 0))
        if base_weight == 0:
            base_weight = 1

        length = len(p)
        penalty = length / 2000.0
        score = base_weight - penalty

        return {
            "index": idx,
            "text": p,
            "flags": flags,
            "score": score,
            "length": length,
        }

    scored = [
        classify_paragraph(p, i, len(paragraphs)) for i, p in enumerate(paragraphs)
    ]
    selected: set[int] = set()
    total_len = 0

    def try_add(idx: int) -> None:
        nonlocal total_len
        if idx in selected:
            return
        para = scored[idx]
        if total_len + para["length"] > budget_chars:
            return
        selected.add(idx)
        total_len += para["length"]

    intro_idxs = [i for i, p in enumerate(scored) if "intro" in p["flags"]]
    for i in intro_idxs[:2]:
        try_add(i)

    concl_idxs = [i for i, p in enumerate(scored) if "conclusion" in p["flags"]]
    for i in concl_idxs[:2]:
        try_add(i)

    remaining = [p for p in scored if p["index"] not in selected]
    remaining.sort(key=lambda x: x["score"], reverse=True)
    for para in remaining:
        if total_len >= budget_chars:
            break
        try_add(para["index"])

    if not selected:
        return text[:budget_chars]

    final_idxs = sorted(selected)
    selected_paras = [paragraphs[i] for i in final_idxs]
    return "\n\n".join(selected_paras)


def structured_paragraphs_truncation(
    payload: Any,
    *,
    budget_chars: int,
    per_item_key: str = "content",
    max_chars_per_item: int = 1800,
    **_: Any,
) -> Any:
    """针对“列表 + 每条有 content 字段”的 payload 做结构化截断。"""
    if not isinstance(payload, list):
        return payload

    remaining_budget = budget_chars
    result: List[dict] = []

    for item in payload:
        if not isinstance(item, dict):
            result.append(item)
            continue

        raw = item.get(per_item_key)
        if not raw or not isinstance(raw, str):
            result.append(item)
            continue

        per_budget = min(max_chars_per_item, remaining_budget)
        if per_budget <= 0:
            truncated = raw[: min(400, len(raw))]
        else:
            truncated = _select_representative_paragraphs(raw, budget_chars=per_budget)

        new_item = dict(item)
        new_item[per_item_key] = truncated
        result.append(new_item)

        remaining_budget -= len(truncated)
        if remaining_budget <= 0:
            break

    if len(result) < len(payload):
        for rest in payload[len(result) :]:
            if isinstance(rest, dict):
                stripped = dict(rest)
                stripped.pop(per_item_key, None)
                result.append(stripped)
            else:
                result.append(rest)

    return result


@dataclass
class ContextBudget:
    """统一做上下文预算和压缩的管理器。"""

    max_context_tokens: int
    max_output_tokens: int = 3000
    safety_ratio: float = 0.8
    task_name: Optional[str] = None
    per_task_limits: Dict[str, Any] = field(default_factory=dict)
    blocks: List[ContextBlock] = field(default_factory=list)
    strategies: Dict[str, TruncationStrategy] = field(
        default_factory=lambda: {
            "structured_paragraphs": structured_paragraphs_truncation,
        }
    )

    def add_block(self, block: ContextBlock) -> None:
        block.estimated_chars = estimate_chars(block.payload)
        self.blocks.append(block)

    @property
    def input_budget_chars(self) -> int:
        usable_tokens = (
            int(self.max_context_tokens * self.safety_ratio) - self.max_output_tokens
        )
        if usable_tokens <= 0:
            usable_tokens = int(self.max_context_tokens * self.safety_ratio * 0.8)
        return max(usable_tokens * 4, 2000)

    def summarize_usage(self) -> Dict[str, int]:
        return {b.name: b.estimated_chars for b in self.blocks}

    def _apply_truncation(self) -> None:
        total_chars = sum(b.estimated_chars for b in self.blocks)
        budget = self.input_budget_chars

        if total_chars <= budget:
            return

        candidates = [b for b in self.blocks if b.truncatable and b.strategy_name]
        candidates.sort(key=lambda b: b.priority)

        task_limit = self.per_task_limits.get(self.task_name or "", {})
        materials_ratio = float(task_limit.get("max_input_ratio", 0.6))
        materials_budget = int(budget * materials_ratio)

        for block in candidates:
            if total_chars <= budget:
                break

            strategy = self.strategies.get(block.strategy_name)  # type: ignore[arg-type]
            if not strategy:
                continue

            block_share = int(
                materials_budget * (block.estimated_chars / max(total_chars, 1))
            )
            if block_share <= 0:
                block_share = min(block.estimated_chars, materials_budget)

            new_payload = strategy(
                block.payload,
                budget_chars=block_share,
                **block.strategy_params,
            )
            block.payload = new_payload
            block.estimated_chars = estimate_chars(new_payload)

            total_chars = sum(b.estimated_chars for b in self.blocks)

    def compact(self) -> None:
        self._apply_truncation()

    def get_block_payload(self, name: str) -> Any:
        for b in self.blocks:
            if b.name == name:
                return b.payload
        raise KeyError(f"Block '{name}' not found")


__all__ = [
    "ContextBudget",
    "ContextBlock",
    "structured_paragraphs_truncation",
]
