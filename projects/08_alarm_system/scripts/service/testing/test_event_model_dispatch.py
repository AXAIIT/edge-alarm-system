"""Ordering/compatibility tests. Fake responses are NOT model acceptance."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[3]
sys.path.insert(0, str(SERVICE))
sys.path.insert(0, str(SERVICE.parent / "run_demo"))
sys.path.insert(0, str(SERVICE.parent / "benchmark"))
from common import parse_simple_yaml
from event_model_dispatch import dispatch_event_models
from text_worker import ServiceTextWorker
from vlm_worker import ServiceVlmWorker
from run_event_trigger import build_event, load_rule_config
from validate_alarm_jsonl import check_schema_specific
from llm_prompt_policy import rule_explanation
from build_alarm_json import build_alarm
from detector_service import normalize_event_route
from run_alarm_system_benchmark import build_raw_row


def make_event():
    rules = load_rule_config(REPO / "projects/08_alarm_system/configs/event_rules/jetson_rules.yaml")
    detections = [
        {"class_id": 0, "class_name": "person", "confidence": .82, "bbox": [1, 2, 18, 25]},
        {"class_id": 2, "class_name": "car", "confidence": .88, "bbox": [20, 2, 45, 30]},
    ]
    return build_event({"frame_id": 7, "target": "jetson_8gb", "frame_width": 64,
                        "frame_height": 48}, "dispatch_test", 1, rules, rules["rules"][2], detections)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.combo = parse_simple_yaml(REPO / "projects/08_alarm_system/configs/models/jetson_model_combo.yaml")
        self.calls = []
        self.text = ServiceTextWorker("template", self.combo, argparse.Namespace(text_max_calls=0), Path("unused.jsonl"))
        self.vlm = ServiceVlmWorker("stub", self.combo["image_vlm"], argparse.Namespace(vlm_max_calls=0), Path("unused.jsonl"))
        self.asset = Mock()
        self.asset.enrich.side_effect = self.enrich
        self.vlm.should_prepare_assets = Mock(return_value=True)
        self.text.explain = Mock(side_effect=self.explain)
        self.vlm.review = Mock(side_effect=self.review)
        self.gate = Mock(enabled=True)
        self.gate.evaluate.side_effect = self.evaluate
        self.rejected = set()
        self.vlm_status = "pass"
        self.text_status = "pass"

    def enrich(self, event):
        self.calls.append("asset")
        return dict(event, keyframe_path="event_keyframe.jpg", context_crop_path="event_context.jpg")

    def evaluate(self, worker, *context):
        self.calls.append("gate:" + worker)
        return {"allowed": worker not in self.rejected, "worker": worker, "snapshot": {}, "reasons": []}

    def explain(self, event, timestamp):
        self.calls.append("text")
        raw = rule_explanation(event)
        return {"event_id": event["event_id"], "status": self.text_status,
                "llm_explanation": raw, "llm_raw_output": raw}

    def review(self, event, timestamp):
        self.calls.append("vlm")
        return {"event_id": event["event_id"], "status": self.vlm_status,
                "vlm_summary": "图中有人员和车辆。" if self.vlm_status == "pass" else None}

    def dispatch(self, event=None, **options):
        defaults = dict(text_worker=self.text, vlm_worker=self.vlm, asset_worker=self.asset,
                        resource_gate=self.gate, gate_context=lambda: (0, 30.0, True),
                        text_real_calls_enabled=True, vlm_real_calls_enabled=True,
                        asset_mode="source_media")
        return dispatch_event_models(make_event() if event is None else event, **dict(defaults, **options))

    def test_default_multi_object_calls_text_then_asset_then_vlm(self):
        result = self.dispatch()
        self.assertEqual(result["event"]["route_target"], "text_then_vlm")
        self.assertEqual(self.calls, ["gate:text", "text", "gate:vlm", "asset", "vlm"])
        self.text.explain.assert_called_once()
        self.vlm.review.assert_called_once()
        self.assertNotIn("vlm_summary", self.text.explain.call_args.args[0])

    def test_explicit_visual_first_keeps_dependency_and_summary(self):
        self.dispatch(dict(make_event(), route_target="vlm_then_text"))
        self.assertEqual(self.calls, ["gate:vlm", "asset", "vlm", "gate:text", "text"])
        self.assertEqual(self.text.explain.call_args.args[0]["vlm_review_status"], "pass")

    def test_explicit_visual_first_failed_vlm_blocks_text(self):
        self.vlm_status = "fail"
        result = self.dispatch(dict(make_event(), route_target="vlm_then_text"))
        self.text.explain.assert_not_called()
        self.assertEqual(result["text_route"]["reason"], "upstream_vlm_not_pass")

    def test_new_default_does_not_require_future_vlm_success(self):
        self.vlm_status = "fail"
        result = self.dispatch()
        self.assertEqual(result["llm_row"]["status"], "pass")
        self.assertEqual(result["vlm_row"]["status"], "fail")

    def test_text_failure_does_not_remove_visual_review(self):
        self.text_status = "fail"
        result = self.dispatch()
        self.assertEqual(result["llm_row"]["status"], "fail")
        self.assertEqual(result["vlm_row"]["status"], "pass")

    def test_text_resource_rejection_keeps_visual_gate(self):
        self.rejected.add("text")
        result = self.dispatch()
        self.text.explain.assert_not_called()
        self.vlm.review.assert_called_once()
        self.assertEqual(result["llm_row"]["status"], "not_executed")

    def test_visual_resource_rejection_does_not_read_images(self):
        self.rejected.add("vlm")
        result = self.dispatch()
        self.text.explain.assert_called_once()
        self.vlm.review.assert_not_called()
        self.asset.enrich.assert_not_called()
        self.assertEqual(result["asset_skipped_events"], 1)

    def test_old_routes_keep_exact_model_selection(self):
        for route, expected in [("rule_only", []), ("template_only", []),
                                ("text_only", ["text"]), ("vlm_only", ["vlm"])]:
            with self.subTest(route=route):
                self.calls.clear()
                self.dispatch(dict(make_event(), route_target=route))
                self.assertEqual([x for x in self.calls if x in {"text", "vlm"}], expected)

    def test_prepared_assets_not_read_twice(self):
        result = self.dispatch(dict(make_event(), __asset_prepared=True))
        self.asset.enrich.assert_not_called()
        self.assertEqual(result["asset_skipped_events"], 0)
        self.assertNotIn("__asset_prepared", result["event"])

    def test_visual_cooldown_or_budget_does_not_prepare_assets(self):
        self.vlm.should_prepare_assets.return_value = False
        self.dispatch()
        self.asset.enrich.assert_not_called()
        # The unchanged worker remains responsible for cooldown/budget fallback.
        self.vlm.review.assert_called_once()

    def test_duplicate_text_request_not_reissued(self):
        event = make_event()
        self.text.seen_request_keys.add(self.text.model_request_key(event))
        result = self.dispatch(event)
        self.text.explain.assert_not_called()
        self.assertEqual(result["text_route"]["reason"], "duplicate_model_request_key")

    def test_duplicate_visual_request_does_not_prepare_assets(self):
        event = make_event()
        self.vlm.seen_request_keys.add(self.vlm.model_request_key(event))
        self.dispatch(event)
        self.asset.enrich.assert_not_called()
        self.vlm.review.assert_not_called()
        self.text.explain.assert_called_once()

    def test_input_is_not_mutated_and_output_keeps_structured_alarm(self):
        event = make_event()
        before = copy.deepcopy(event)
        result = self.dispatch(event)
        self.assertEqual(event, before)
        alarm = build_alarm(result["event"], self.combo, {event["event_id"]: result["llm_row"]},
                            {event["event_id"]: result["vlm_row"]}, {}, "raw.jsonl")
        self.assertEqual(alarm["route_target"], "text_then_vlm")
        self.assertEqual(alarm["risk_level"], event["risk_level"])
        self.assertFalse(alarm["json_fact_conflict"])
        self.assertEqual(len(alarm["detections"]), 2)

    def test_new_and_old_routes_pass_schema_and_business_checker(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema unavailable; full schema test runs on the host")
        schema_dir = REPO / "projects/08_alarm_system/configs/alarm_schema"
        schema = json.loads((schema_dir / "alarm_event_package_schema.json").read_text(encoding="utf-8"))
        for route in ["text_then_vlm", "vlm_then_text"]:
            event = dict(make_event(), route_target=route)
            errors = []
            check_schema_specific(event, "alarm_event_package_schema.json", "event", errors)
            self.assertEqual(errors, [])
            jsonschema.validate(event, schema)
            result = self.dispatch(event)
            alarm = build_alarm(result["event"], self.combo, {event["event_id"]: result["llm_row"]},
                                {event["event_id"]: result["vlm_row"]}, {}, "raw.jsonl")
            alarm_schema = json.loads((schema_dir / "alarm_event_schema.json").read_text(encoding="utf-8"))
            jsonschema.validate(alarm, alarm_schema)
            raw = build_raw_row(event, alarm, self.combo, "jetson_8gb", "test_only", Path("events.jsonl"), Path("alarms.jsonl"))
            raw_schema = json.loads((schema_dir / "alarm_system_raw_schema.json").read_text(encoding="utf-8"))
            jsonschema.validate(raw, raw_schema)

    def test_default_jetson_rule_and_wake_routes(self):
        ruleset = load_rule_config(REPO / "projects/08_alarm_system/configs/event_rules/jetson_rules.yaml")
        routes = {rule["rule_id"]: rule["route_target"] for rule in ruleset["rules"]}
        self.assertEqual(routes["person_presence_candidate"], "rule_only")
        self.assertEqual(routes["vehicle_presence_candidate"], "rule_only")
        self.assertEqual(routes["multi_object_scene_candidate"], "text_then_vlm")
        self.assertEqual(
            self.combo["text_llm"]["scheduler"]["wake_route_targets"],
            ["text_only", "text_then_vlm", "vlm_then_text"],
        )
        self.assertEqual(
            self.combo["image_vlm"]["scheduler"]["wake_route_targets"],
            ["vlm_only", "text_then_vlm", "vlm_then_text"],
        )

    def test_replay_normalizer_preserves_new_and_legacy_routes(self):
        event = make_event()
        normalized = normalize_event_route(event)
        self.assertEqual(normalized["route_target"], "text_then_vlm")
        self.assertTrue(normalized["needs_text"])
        self.assertTrue(normalized["needs_vlm"])
        self.assertEqual(normalized["evidence_hash"], event["evidence_hash"])
        legacy = dict(event)
        for key in ["route_target", "text_purpose", "vlm_purpose"]:
            legacy.pop(key)
        normalized = normalize_event_route(legacy)
        self.assertEqual(normalized["route_target"], "vlm_then_text")
        self.assertEqual(normalized["text_purpose"], "post_vlm_alarm_explanation")


if __name__ == "__main__":
    unittest.main()
