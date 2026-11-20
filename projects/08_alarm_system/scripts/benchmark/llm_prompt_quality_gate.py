#!/usr/bin/env python3
"""Versioned, fail-closed quality gate for Project 08 prompt experiments.

This is an experiment evaluator, not a publisher or a production fact guard.
It never rewrites output or infers risk from detections. Unreviewed language
needs review and cannot silently become a quality pass.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


GATE_VERSION = "p08_prompt_quality_v2"
LABELS = ("触发原因", "风险等级", "建议动作", "证据限制")
RISK_ALIASES = {
    "info": {"info", "信息", "信息级", "提示"},
    "low": {"low", "低", "低风险"},
    "medium": {"medium", "中", "中等", "中风险"},
    "high": {"high", "高", "高风险"},
    "critical": {"critical", "极高", "极高风险", "危急"},
}
ACTION_ALIASES = {
    "notify_operator": {"notify_operator", "通知操作员", "通知值守人员", "上报操作员", "通知人工值守"},
    "inspect_site": {"inspect_site", "检查现场", "现场检查", "现场复核", "人工复核", "核查现场"},
    "observe": {"observe", "观察", "持续观察", "记录事件", "观察并记录事件", "持续观察并记录事件"},
    "no_action": {"no_action", "无需行动", "无需采取额外动作", "不采取额外动作"},
}
CLASS_ALIASES = {
    "person": ("person", "人员", "行人", "人体", "人"),
    "car": ("car", "汽车", "轿车"),
    "bus": ("bus", "公交车", "巴士"),
    "truck": ("truck", "货车", "卡车"),
    "motorcycle": ("motorcycle", "摩托车"),
    "bicycle": ("bicycle", "自行车"),
    "dog": ("dog", "狗"),
    "cat": ("cat", "猫"),
    "vehicle": ("vehicle", "车辆", "机动车"),
}
VEHICLE_CLASSES = {"car", "bus", "truck", "motorcycle", "bicycle"}
INTERNAL_FIELDS = (
    "benchmark_nonce", "event_id", "class_id", "alarm_domain", "alarm_type",
    "risk_level", "risk_basis", "allowed_actions", "trigger_rule_id", "trigger_reason",
    "detections", "confidence_threshold", "duration_frames", "cooldown_seconds", "bbox", "vlm_summary",
)
UNSUPPORTED_CLAIMS = (
    "冲突", "打架", "斗殴", "奔跑", "徘徊", "跌倒", "摔倒", "火焰", "明火", "烟雾",
    "武器", "持刀", "违法", "未佩戴", "安全帽", "头盔", "身份已确认", "身份确认",
    "危险行为", "异常行为", "入侵", "违停", "靠近", "左侧", "右侧",
)
NUMBER_WORDS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
NUMBER_TEXT = r"(?:\d+|[零一二两三四五六七八九十])"
CONFIDENCE_RE = re.compile(
    r"(?:置信度|confidence)\s*(?:为|是|=|[:：])?\s*(-?\d+(?:\.\d+)?)(\s*[%％])?", re.I
)
TARGET_RE = re.compile(r"目标\s*(\d+)")


def _clean(value: str) -> str:
    return value.strip().rstrip("。.!！ ").strip()


def _number(value: str) -> int:
    return int(value) if value.isdigit() else NUMBER_WORDS[value]


def _alias_pattern(aliases: list[str]) -> str:
    pieces = []
    for alias in sorted(set(aliases), key=len, reverse=True):
        escaped = re.escape(alias)
        if alias.isascii() and (alias[0].isalnum() or alias[0] == "_"):
            pieces.append(r"(?<![A-Za-z0-9_])" + escaped + r"(?![A-Za-z0-9_])")
        else:
            pieces.append(escaped)
    return "|".join(pieces)


def _class_mentions(text: str, event: dict[str, Any]) -> list[dict[str, Any]]:
    alias_map = {alias.lower(): key for key, aliases in CLASS_ALIASES.items() for alias in aliases}
    for det in event.get("detections") or []:
        name = str(det.get("class_name") or "").lower()
        if name:
            alias_map[name] = name
    pattern = _alias_pattern(list(alias_map))
    return [{"class": alias_map[m.group().lower()], "start": m.start(), "end": m.end()}
            for m in re.finditer(pattern, text, re.I)]


def _class_matches(key: str, expected: set[str]) -> bool:
    return bool(expected & VEHICLE_CLASSES) if key == "vehicle" else key in expected


def _parse_actions(value: str) -> tuple[list[str], list[str]]:
    aliases = {alias.lower(): key for key, values in ACTION_ALIASES.items() for alias in values}
    normalized = _clean(value).lower()
    if normalized in aliases:
        return [aliases[normalized]], []
    parts = re.split(r"[、，,；;]+|\s+(?:and|or)\s+|并且|以及|然后|并|和|或|且", normalized)
    actions, unknown = [], []
    for part in parts:
        part = _clean(part)
        if part in aliases:
            actions.append(aliases[part])
        else:
            unknown.append(part or "<empty action>")
    return actions, unknown


def _input_errors(event: dict[str, Any]) -> list[str]:
    errors = []
    if not isinstance(event.get("risk_level"), str) or event["risk_level"] not in RISK_ALIASES:
        errors.append("input_risk_missing_or_invalid")
    allowed = event.get("allowed_actions")
    if not isinstance(allowed, list) or not allowed or any(not isinstance(action, str) or action not in ACTION_ALIASES for action in allowed):
        errors.append("input_allowed_actions_missing_or_invalid")
    detections = event.get("detections")
    if not isinstance(detections, list):
        errors.append("input_detections_not_array")
        return errors
    for i, det in enumerate(detections, 1):
        if not isinstance(det, dict) or not isinstance(det.get("class_name"), str) or not det["class_name"].strip():
            errors.append(f"input_class_missing:target{i}")
            continue
        try:
            confidence = Decimal(str(det["confidence"]))
            if not confidence.is_finite() or not Decimal(0) <= confidence <= Decimal(1):
                raise ValueError
        except (KeyError, InvalidOperation, ValueError):
            errors.append(f"input_confidence_invalid:target{i}")
    return errors


def _fact_errors(reason: str, event: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors, reviews = [], []
    detections = event["detections"]
    expected = {str(det["class_name"]).lower() for det in detections}
    targets = list(TARGET_RE.finditer(reason))
    for match in targets:
        if not 1 <= int(match[1]) <= len(detections):
            errors.append(f"target_not_in_event:{match[1]}")
    mentions = _class_mentions(reason, event)
    for mention in mentions:
        if not _class_matches(mention["class"], expected):
            errors.append(f"class_not_in_event:{mention['class']}")
        preceding = [m for m in targets if m.end() <= mention["start"]]
        if preceding:
            idx = int(preceding[-1][1]) - 1
            if 0 <= idx < len(detections) and not _class_matches(
                mention["class"], {str(detections[idx]["class_name"]).lower()}
            ):
                errors.append(f"class_target_mismatch:target{idx + 1}")
    for match in CONFIDENCE_RE.finditer(reason):
        observed = Decimal(match[1]) / (100 if match[2] else 1)
        preceding = [m for m in targets if m.end() <= match.start()]
        if preceding:
            idx = int(preceding[-1][1]) - 1
            expected_values = [Decimal(str(detections[idx]["confidence"]))] if 0 <= idx < len(detections) else []
        elif len(detections) == 1:
            expected_values = [Decimal(str(detections[0]["confidence"]))]
        else:
            expected_values = []
            reviews.append("confidence_target_binding_not_explicit")
        if observed not in expected_values:
            errors.append(f"confidence_mismatch:{observed}")
    count_pattern = re.compile(rf"({NUMBER_TEXT})\s*(名|辆|个|只)\s*(人员|行人|人|车辆|汽车|轿车|货车|卡车|公交车|巴士|摩托车|自行车|目标|狗|猫)")
    alias_to_key = {a: key for key, aliases in CLASS_ALIASES.items() for a in aliases}
    for match in count_pattern.finditer(reason):
        count = _number(match[1])
        key = alias_to_key.get(match[3])
        expected_count = len(detections) if match[3] == "目标" else sum(
            _class_matches(key or "", {str(det["class_name"]).lower()}) for det in detections
        )
        if count != expected_count:
            errors.append(f"detection_count_mismatch:{count}!={expected_count}")
    for match in re.finditer(rf"(?:目标数量|检测数量|目标总数)\s*(?:为|是|=|[:：])\s*({NUMBER_TEXT})", reason):
        if _number(match[1]) != len(detections):
            errors.append("detection_total_mismatch")
    for claim in UNSUPPORTED_CLAIMS:
        if claim in reason:
            errors.append(f"unsupported_claim:{claim}")
    if detections and re.search(r"未检测到|无有效目标|没有目标|未发现目标", reason):
        errors.append("denies_existing_detections")
    if not detections and reason not in {"未检测到符合条件的目标", "未检测到有效目标", "无有效检测目标"}:
        errors.append("empty_detection_reason_not_supported")
    if detections and not mentions and not targets and not count_pattern.search(reason):
        errors.append("reason_has_no_specific_detection_fact")

    # Recognized factual language is audited; unknown prose is a review item.
    # No claim is accepted merely because it avoids a blacklist.
    residue = CONFIDENCE_RE.sub("", reason)
    residue = TARGET_RE.sub("", residue)
    residue = count_pattern.sub("", residue)
    residue = re.sub(rf"(?:目标数量|检测数量|目标总数)\s*(?:为|是|=|[:：])\s*{NUMBER_TEXT}", "", residue)
    residue = re.sub(_alias_pattern([str(det["class_name"]).lower() for det in detections]
                                   + [a for values in CLASS_ALIASES.values() for a in values]), "", residue, flags=re.I)
    if event.get("alarm_type"):
        residue = residue.replace(str(event["alarm_type"]), "")
    for word in sorted(("未检测到符合条件的目标", "未检测到有效目标", "无有效检测目标", "检测到", "检测结果", "检测事实", "目标数量", "规则命中", "告警类型", "类别为", "类别", "存在", "目标", "数量", "符合条件", "本次", "和", "与", "及", "为", "是"), key=len, reverse=True):
        residue = residue.replace(word, "")
    residue = re.sub(r"[\s,，。.!！:：;；、()（）\[\]【】=]+", "", residue)
    if residue:
        reviews.append(f"reason_expression_needs_review:{residue}")
    return errors, reviews


def validate_output(event: dict[str, Any], output: str, *, mode: str = "llm") -> dict[str, Any]:
    """Validate raw text without repairing it or changing the event policy."""
    if not isinstance(event, dict):
        return {"gate_version": GATE_VERSION, "accepted": False, "status": "fail",
                "errors": ["input_event_not_object"], "review_items": [],
                "fields": {}, "recognized_actions": []}
    errors = _input_errors(event)
    reviews: list[str] = []
    fields: dict[str, str] = {}
    if mode not in {"llm", "rule_bypass"}:
        errors.append("invalid_execution_mode")
    if isinstance(event.get("detections"), list) and not event["detections"] and mode != "rule_bypass":
        errors.append("empty_detection_must_bypass_llm")
    if mode == "rule_bypass" and event.get("detections"):
        errors.append("nonempty_event_cannot_use_empty_detection_bypass")
    if not isinstance(output, str):
        errors.append("output_not_text")
        output = ""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != 4:
        errors.append(f"four_line_contract:{len(lines)}")
    for i, line in enumerate(lines):
        match = re.fullmatch(r"(?:(\d+)[)）.、]\s*)?(触发原因|风险等级|建议动作|证据限制)\s*[:：]\s*(.+)", line)
        if match is None:
            errors.append(f"invalid_or_empty_field:line{i + 1}")
            continue
        label, value = match[2], match[3].strip()
        if i >= len(LABELS) or label != LABELS[i] or (match[1] and int(match[1]) != i + 1):
            errors.append(f"label_order_or_number:line{i + 1}")
        if label in fields:
            errors.append(f"duplicate_label:{label}")
        if any(re.search(re.escape(other) + r"\s*[:：]", value) for other in LABELS):
            errors.append(f"nested_label:{label}")
        if not value or not _clean(value):
            errors.append(f"empty_field:{label}")
        fields[label] = value
    for label in LABELS:
        if label not in fields:
            errors.append(f"missing_field:{label}")
    for field in INTERNAL_FIELDS:
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(field) + r"(?![A-Za-z0-9_])", output, re.I):
            errors.append(f"internal_field_leak:{field}")
    if re.search(r"<\/?think>|\[Start thinking\]|\[End thinking\]|/no_think", output, re.I):
        errors.append("reasoning_or_control_marker_leak")

    if isinstance(event.get("risk_level"), str) and event["risk_level"] in RISK_ALIASES and "风险等级" in fields:
        value = _clean(fields["风险等级"]).lower()
        if value not in RISK_ALIASES[event["risk_level"]]:
            errors.append("risk_not_exact_event_value")
    actions: list[str] = []
    if "建议动作" in fields:
        actions, unknown = _parse_actions(fields["建议动作"])
        if unknown:
            errors.append("unrecognized_or_additional_action:" + "|".join(unknown))
        allowed = event.get("allowed_actions")
        if isinstance(allowed, list) and all(isinstance(a, str) for a in allowed) and (not actions or not set(actions).issubset(set(allowed))):
            errors.append("action_not_in_allowed_set")
    if not _input_errors(event) and "触发原因" in fields:
        fact_errors, fact_reviews = _fact_errors(fields["触发原因"], event)
        errors.extend(fact_errors)
        reviews.extend(fact_reviews)
    if "证据限制" in fields:
        evidence = _clean(fields["证据限制"])
        if evidence in {"无", "没有", "无证据限制", "没有限制", "无任何限制", "不限"}:
            errors.append("evidence_boundary_missing")
        elif not re.match(r"(?:仅(?:限于|限|依据|基于)|只(?:依据|基于)|依据本次|基于本次)", evidence):
            reviews.append("evidence_boundary_expression_needs_review")
        else:
            if not re.search(r"检测|置信度|事件包|输入|目标\s*\d+", evidence):
                reviews.append("evidence_scope_not_identified")
            for ref in TARGET_RE.finditer(evidence):
                detections = event.get("detections")
                if not isinstance(detections, list) or not 1 <= int(ref[1]) <= len(detections):
                    errors.append(f"evidence_target_not_in_event:{ref[1]}")
            for claim in UNSUPPORTED_CLAIMS:
                if claim in evidence:
                    errors.append(f"unsupported_evidence_claim:{claim}")
            if re.search(r"已确认|证明|证实|无限制|完整证据|全部证据|视频|图像|图片|人工确认", evidence):
                reviews.append("evidence_claim_exceeds_detector_only_contract")
            # Evidence prose has its own bounded vocabulary. An unknown sentence
            # after a valid prefix is not accepted through keyword matching.
            residue = re.sub(r"^(?:仅(?:限于|限|依据|基于)|只(?:依据|基于)|依据本次|基于本次)", "", evidence)
            residue = TARGET_RE.sub("", residue)
            for phrase in sorted(("未检测到有效目标", "未检测到符合条件的目标", "不推断行为", "不推断身份", "不推断场景原因", "不判断行为", "检测事实", "检测结果", "检测数据", "置信度数据", "事件包", "检测", "事实", "结果", "证据", "输入", "数据", "本次", "行为", "身份", "场景原因", "目标", "仅", "限于", "和", "与", "及", "或", "的"), key=len, reverse=True):
                residue = residue.replace(phrase, "")
            residue = re.sub(r"[\s,，。.!！:：;；、()（）]+", "", residue)
            if residue:
                reviews.append(f"evidence_expression_needs_review:{residue}")
            if not _input_errors(event):
                evidence_errors, _ = _fact_errors(evidence, event)
                ignored = {"reason_has_no_specific_detection_fact", "empty_detection_reason_not_supported"}
                errors.extend("evidence_" + error for error in evidence_errors if error not in ignored)
    errors = list(dict.fromkeys(errors))
    reviews = list(dict.fromkeys(reviews))
    return {"gate_version": GATE_VERSION,
            "accepted": not errors and not reviews,
            "status": "fail" if errors else "needs_review" if reviews else "pass",
            "errors": errors, "review_items": reviews, "fields": fields,
            "recognized_actions": actions}
