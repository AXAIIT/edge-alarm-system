"""Route-specific ordering; retain the workers' existing gates and fallbacks."""
from __future__ import annotations

from typing import Any, Callable

from common import utc_now_iso


def dispatch_event_models(
    event: dict[str, Any],
    *,
    text_worker: Any,
    vlm_worker: Any,
    asset_worker: Any,
    resource_gate: Any,
    gate_context: Callable[[], tuple[int, float | None, bool | None]],
    text_real_calls_enabled: bool,
    vlm_real_calls_enabled: bool,
    asset_mode: str,
) -> dict[str, Any]:
    """Run each existing stage once, then return the same publication inputs.

    Only text_then_vlm runs Text first. Explicit vlm_then_text and all old
    single-model/rule routes keep the original order and upstream dependency.
    No second Text call, independent queue or intermediate publication is added.
    """
    event = dict(event)
    asset_prepared = bool(event.pop("__asset_prepared", False))
    asset_skipped = 0
    llm_row = vlm_row = None
    text_route = text_gate = vlm_route = vlm_gate = None

    def evaluate(worker: str, enabled: bool, route: dict[str, Any]) -> dict[str, Any]:
        if enabled and route["allowed"]:
            return resource_gate.evaluate(worker, *gate_context())
        label = "vlm" if worker == "vlm" else "text"
        return {
            "enabled": resource_gate.enabled,
            "worker": worker,
            "allowed": True,
            "reasons": [f"real_{label}_call_disabled_or_route_skipped"],
            "snapshot": {},
        }

    def run_text() -> None:
        nonlocal llm_row, text_route, text_gate
        text_event = dict(event)
        if vlm_row is not None:
            text_event["vlm_review_status"] = vlm_row.get("status")
            text_event["vlm_summary"] = vlm_row.get("vlm_summary")
            text_event["vlm_mode"] = vlm_row.get("mode")
        text_route = text_worker.route_decision(text_event)
        text_gate = evaluate("text", text_real_calls_enabled, text_route)
        timestamp = utc_now_iso()
        if not text_route["allowed"]:
            llm_row = text_worker.route_fallback(text_event, timestamp, text_route)
        elif text_real_calls_enabled and not text_gate["allowed"]:
            llm_row = text_worker.resource_gate_fallback(text_event, timestamp, text_gate)
        else:
            llm_row = text_worker.explain(text_event, timestamp)

    def run_vlm() -> None:
        nonlocal event, vlm_row, vlm_route, vlm_gate, asset_skipped
        timestamp = utc_now_iso()
        vlm_route = vlm_worker.route_decision(event)
        vlm_gate = evaluate("vlm", vlm_real_calls_enabled, vlm_route)
        should_prepare_assets = (
            asset_mode == "source_media"
            and vlm_real_calls_enabled
            and vlm_route["allowed"]
            and vlm_gate["allowed"]
            and vlm_worker.should_prepare_assets()
        )
        if should_prepare_assets and not asset_prepared:
            event = asset_worker.enrich(event)
        elif asset_mode == "source_media" and not asset_prepared:
            asset_skipped += 1
        if not vlm_route["allowed"]:
            vlm_row = vlm_worker.route_fallback(event, timestamp, vlm_route)
        elif vlm_real_calls_enabled and not vlm_gate["allowed"]:
            vlm_row = vlm_worker.resource_gate_fallback(event, timestamp, vlm_gate)
        else:
            vlm_row = vlm_worker.review(event, timestamp)

    if event.get("route_target") == "text_then_vlm":
        run_text()
        run_vlm()
    else:
        run_vlm()
        run_text()

    return {
        "event": event, "llm_row": llm_row, "vlm_row": vlm_row,
        "text_route": text_route, "vlm_route": vlm_route,
        "text_gate": text_gate, "vlm_gate": vlm_gate,
        "asset_skipped_events": asset_skipped,
    }
