#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

RUN_DEMO_DIR = Path(__file__).resolve().parents[2] / "run_demo"
if str(RUN_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DEMO_DIR))

from build_alarm_json import build_alarm  # noqa: E402
from fact_guard import validate_llm_explanation  # noqa: E402


EVENT = {
    "event_id": "fact_guard_person_001",
    "board": "Jetson 8GB",
    "target": "jetson_8gb",
    "alarm_domain": "visual_detection",
    "alarm_type": "person_presence",
    "detections": [{"class_name": "person", "confidence": 0.766, "bbox": [1, 2, 3, 4]}],
    "trigger_reason": {"confidence_threshold": 0.6},
}


def main() -> int:
    valid = (
        "1) 触发原因：检测到人员，置信度 0.766。\n"
        "2) 风险等级：high\n"
        "3) 建议动作：记录事件并人工复核。\n"
        "4) 证据限制：仅依据本次检测结果。"
    )
    assert validate_llm_explanation(EVENT, valid, "high").accepted

    compact_valid = "1) 人体检测；2) 高风险；3) 记录事件并人工复核；4) 仅依据检测结果。"
    compact_result = validate_llm_explanation(EVENT, compact_valid, "high")
    assert compact_result.accepted
    assert compact_result.published_text and "\n" in compact_result.published_text

    drifted = (
        "1) 触发原因：检测到车辆且未佩戴安全帽。\n"
        "2) 风险等级：medium\n"
        "3) 建议动作：检查异常行为。\n"
        "4) 证据限制：仅限检测区域。"
    )
    assert not validate_llm_explanation(EVENT, drifted, "high").accepted
    alarm = build_alarm(
        EVENT,
        {"text_llm": {}, "image_vlm": {}, "video_vlm": {}},
        {EVENT["event_id"]: {"status": "pass", "llm_explanation": drifted}},
        {},
        {},
        "test.jsonl",
    )
    assert alarm["json_fact_conflict"] is True
    assert "未佩戴安全帽" not in alarm["llm_explanation"]
    assert alarm["fallback_status"]["alarm_json"] == "fact_conflict_detected"
    print("fact_guard_test=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
