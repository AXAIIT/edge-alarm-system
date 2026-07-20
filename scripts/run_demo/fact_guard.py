#!/usr/bin/env python3
"""Deterministic guard for LLM text attached to Project 05 alarms."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


FORBIDDEN_UNSUPPORTED_CLAIMS = (
    "未识别",
    "安全帽",
    "头盔",
    "未佩戴",
    "跌倒",
    "摔倒",
    "火焰",
    "明火",
    "烟雾",
    "打架",
    "奔跑",
    "徘徊",
    "聚集",
    "武器",
    "异常行为",
)

CLASS_ALIASES = {
    "person": ("person", "人员", "行人", "人体"),
    "car": ("car", "vehicle", "车辆", "汽车", "机动车"),
    "bus": ("bus", "公交车", "巴士"),
    "truck": ("truck", "货车", "卡车"),
    "motorcycle": ("motorcycle", "摩托车"),
    "bicycle": ("bicycle", "自行车"),
}

RISK_ALIASES = {
    "info": ("info", "信息", "提示"),
    "low": ("low", "低风险", "低"),
    "medium": ("medium", "中风险", "中等", "中"),
    "high": ("high", "高风险", "高"),
    "critical": ("critical", "严重", "极高"),
}


@dataclass(frozen=True)
class FactGuardResult:
    accepted: bool
    detail: str | None = None
    published_text: str | None = None


def _class_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _display_number(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def safe_explanation(event: dict[str, Any], risk_level: str) -> str:
    """Render a publishable explanation directly from detector facts."""
    details = []
    for detection in event.get("detections") or []:
        label = detection.get("class_name") or detection.get("class_id") or "object"
        confidence = detection.get("confidence")
        if confidence is None:
            details.append(str(label))
        else:
            details.append(f"{label}（置信度 {_display_number(confidence)}）")
    summary = "、".join(details) if details else "无有效检测目标"
    return (
        f"1) 触发原因：规则命中 {event.get('alarm_type', 'generic_object_event')}；检测到 {summary}。\n"
        f"2) 风险等级：{risk_level}\n"
        "3) 建议动作：记录事件并由人工复核。\n"
        "4) 证据限制：仅依据本次 detector event package，不推断行为、身份或场景原因。"
    )


def _numbered_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    parts = re.split(r"(?:^|[\n；;])\s*(?=[1-4][)）])", normalized)
    return [part.strip(" \t\n；;") for part in parts if part.strip(" \t\n；;")]


def _section_payloads(text: str) -> list[str]:
    payloads = []
    for line in _numbered_lines(text):
        payload = re.sub(r"^[1-4][)）]\s*", "", line).strip()
        payloads.append(payload)
    return payloads


def _canonicalize_sections(payloads: list[str]) -> str:
    labels = ("触发原因", "风险等级", "建议动作", "证据限制")
    normalized = []
    for index, (label, payload) in enumerate(zip(labels, payloads), start=1):
        payload = re.sub(rf"^{re.escape(label)}\s*[：:]?\s*", "", payload).strip()
        normalized.append(f"{index}) {label}：{payload}")
    return "\n".join(normalized)


def _expected_classes(event: dict[str, Any]) -> set[str]:
    return {
        _class_key(detection.get("class_name") or detection.get("class_id"))
        for detection in event.get("detections") or []
    }


def _validate_class_mentions(text: str, expected_classes: set[str]) -> str | None:
    for class_key, aliases in CLASS_ALIASES.items():
        if not any(alias.lower() in text.lower() for alias in aliases):
            continue
        if class_key not in expected_classes:
            return f"mentions_unsupported_class:{class_key}"
    return None


def _validate_confidence_mentions(text: str, event: dict[str, Any]) -> str | None:
    allowed = []
    for detection in event.get("detections") or []:
        try:
            allowed.append(float(detection.get("confidence")))
        except (TypeError, ValueError):
            pass
    trigger_reason = event.get("trigger_reason") or {}
    for key in ("confidence_threshold", "min_confidence", "threshold"):
        try:
            allowed.append(float(trigger_reason[key]))
        except (KeyError, TypeError, ValueError):
            pass
    for value in re.findall(r"置信度\s*(?:为|=|：|:)?\s*([01](?:\.\d+)?)", text, flags=re.IGNORECASE):
        observed = float(value)
        if not any(abs(observed - expected) < 0.001 for expected in allowed):
            return f"confidence_not_in_event:{observed}"
    return None


def _validate_risk_line(payloads: list[str], risk_level: str) -> str | None:
    if len(payloads) < 2:
        return "missing_risk_level"
    joined = payloads[1].lower()
    expected_aliases = RISK_ALIASES.get(risk_level, (risk_level,))
    if not any(alias.lower() in joined for alias in expected_aliases):
        return f"risk_level_mismatch:expected_{risk_level}"
    return None


def validate_llm_explanation(event: dict[str, Any], explanation: str, risk_level: str) -> FactGuardResult:
    payloads = _section_payloads(explanation)
    if len(payloads) != 4 or any(not payload for payload in payloads):
        return FactGuardResult(False, "invalid_four_line_contract")

    for phrase in FORBIDDEN_UNSUPPORTED_CLAIMS:
        if phrase in explanation:
            return FactGuardResult(False, f"unsupported_claim:{phrase}")
    class_error = _validate_class_mentions(explanation, _expected_classes(event))
    if class_error:
        return FactGuardResult(False, class_error)
    confidence_error = _validate_confidence_mentions(explanation, event)
    if confidence_error:
        return FactGuardResult(False, confidence_error)
    risk_error = _validate_risk_line(payloads, risk_level)
    if risk_error:
        return FactGuardResult(False, risk_error)
    return FactGuardResult(True, published_text=_canonicalize_sections(payloads))
