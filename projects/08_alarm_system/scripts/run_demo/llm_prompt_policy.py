#!/usr/bin/env python3
"""Stage-2 final prompt/R0 policy used by the production text worker."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
from typing import Any

from common import action_from_risk, risk_from_detections

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmark"
if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))
from llm_prompt_quality_gate import ACTION_ALIASES, RISK_ALIASES, validate_output  # noqa: E402

POLICY_ID = "stage2_final_r0_v2"


def prepare_event(event: dict[str, Any]) -> dict[str, Any]:
    """Preserve explicit rule policy; legacy inputs use the existing common map."""
    result = dict(event)
    detections = result.get("detections")
    if not isinstance(detections, list):
        raise ValueError("input_detections_not_array")
    for index, detection in enumerate(detections, 1):
        if not isinstance(detection, dict) or not isinstance(detection.get("class_name"), str) or not detection["class_name"].strip():
            raise ValueError(f"input_class_missing:target{index}")
        try:
            confidence = Decimal(str(detection["confidence"]))
            if not confidence.is_finite() or not Decimal(0) <= confidence <= Decimal(1):
                raise ValueError
        except (KeyError, InvalidOperation, ValueError):
            raise ValueError(f"input_confidence_invalid:target{index}")
    explicit_risk = "risk_level" in result
    risk = result["risk_level"] if explicit_risk else risk_from_detections(detections)
    if not isinstance(risk, str) or risk not in RISK_ALIASES:
        raise ValueError("input_risk_missing_or_invalid")
    allowed = result["allowed_actions"] if "allowed_actions" in result else [action_from_risk(risk)]
    if not isinstance(allowed, list) or not allowed or any(not isinstance(action, str) or action not in ACTION_ALIASES for action in allowed):
        raise ValueError("input_allowed_actions_missing_or_invalid")
    if len(set(allowed)) != len(allowed):
        raise ValueError("input_allowed_actions_duplicate")
    result["risk_level"] = risk
    result["allowed_actions"] = list(allowed)
    result.setdefault("risk_basis", "event_package_policy" if explicit_risk else "legacy_common_risk_mapping")
    result["text_policy_version"] = POLICY_ID
    return result


def policy_fields(event: dict[str, Any]) -> dict[str, Any]:
    return {key: event[key] for key in ("risk_level", "risk_basis", "allowed_actions", "text_policy_version")}


def rule_explanation(event: dict[str, Any]) -> str:
    """Deterministic fallback/empty bypass, never counted as a model success."""
    facts = "；".join(
        f"目标{index}：类别为 {det['class_name']}，置信度为 {det['confidence']}"
        for index, det in enumerate(event["detections"], 1)
    ) or "未检测到符合条件的目标"
    return (f"1) 触发原因：{facts}\n"
            f"2) 风险等级：{event['risk_level']}\n"
            f"3) 建议动作：{event['allowed_actions'][0]}\n"
            "4) 证据限制：仅依据本次检测事实。")


def build_prompt(event: dict[str, Any], *, qwen_no_think: bool = False) -> str:
    # Keep the validated R0 builder byte-equivalent at its model-visible output.
    facts = []
    for index, det in enumerate(event.get("detections") or [], 1):
        facts.append(
            f"目标{index}：类别为 {det.get('class_name') or det.get('class_id')}，"
            f"置信度为 {det.get('confidence')}"
        )
    fact_text = "；".join(facts) if facts else "未检测到符合条件的目标"
    allowed = "、".join(str(value) for value in (event.get("allowed_actions") or []))
    if qwen_no_think:
        output_instruction = (
            "不要输出思考过程、推理过程、分析过程或 [Start thinking]。"
            "只输出四行，每行冒号后必须有非空内容，不能重复标题："
            "1) 触发原因；2) 风险等级；3) 建议动作；4) 证据限制。\n"
        )
    else:
        output_instruction = (
            "最终只输出四行，每行冒号后必须有非空内容，不能重复标题："
            "1) 触发原因；2) 风险等级；3) 建议动作；4) 证据限制。\n"
        )
    prompt = (
        "你是边缘告警解释系统。只根据下面的自然语言检测事实和规则引擎结论解释告警。"
        "不要新增不存在的目标，不要改写类别或置信度，"
        "不要推断行为、身份、装备、违法、火焰、烟雾、跌倒或其他未给出的场景属性。\n"
        + output_instruction
        + "第4行固定输出：4) 证据限制：仅依据本次检测事实。\n"
        + f"告警类型：{event.get('alarm_type')}\n"
        + f"检测事实：{fact_text}\n"
        + f"规则引擎已确定风险等级：{event.get('risk_level')}（只读，不得修改）\n"
        + f"规则引擎允许的动作：{allowed}（只读，只能选择其中一个或多个）\n"
        + "不要输出请求编号、测试编号、内部字段名或本提示中的标签名。\n"
    )
    if qwen_no_think:
        prompt += "/no_think\n"
    return prompt
