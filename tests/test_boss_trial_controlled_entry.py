from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_boss_trial_app.py"


def load_boss_trial_module():
    spec = importlib.util.spec_from_file_location("run_boss_trial_app_controlled_entry", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_use_controlled_trial_workflow_flag_from_payload_or_env(monkeypatch) -> None:
    module = load_boss_trial_module()

    monkeypatch.delenv("MAHJONG_TRIAL_USE_CONTROLLED_WORKFLOW", raising=False)
    assert module.use_controlled_trial_workflow({}) is False
    assert module.use_controlled_trial_workflow({"use_controlled_workflow": True}) is True
    assert module.use_controlled_trial_workflow({"controlled_workflow": "on"}) is True
    assert module.use_controlled_trial_workflow({"use_controlled_workflow": "false"}) is False

    monkeypatch.setenv("MAHJONG_TRIAL_USE_CONTROLLED_WORKFLOW", "1")
    assert module.use_controlled_trial_workflow({}) is True


def test_boss_trial_controlled_analyze_returns_projected_shape_without_llm(monkeypatch) -> None:
    module = load_boss_trial_module()
    for key in ("MAHJONG_LLM_API_KEY", "MAHJONG_LLM_MODEL", "MAHJONG_LLM_PROVIDER", "OPENAI_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    with tempfile.TemporaryDirectory() as temp_dir:
        store = module.TrialStore(Path(temp_dir) / "trial.db")
        service = module.BossTrialService(store)

        result = service.analyze_controlled(
            {
                "sender_name": "张哥",
                "sender_id": "zhang",
                "conversation_id": "controlled_entry",
                "text": "老板，今天有人打麻将吗",
                "now": "2026-06-30T17:00:00+08:00",
                "trace_id": "trace_controlled_entry",
            }
        )

    assert result["controlled_workflow_enabled"] is True
    assert result["legacy_path"] is False
    assert result["workflow"]["engine"] == "controlled_workflow.v1"
    assert result["parsed"]["semantic_action"]["effective_action"] == "human_review"
    assert result["suggested_reply"]["text"] == "这个我先转人工确认一下。"
    assert result["outbox"] == []
    assert result["pool_matches"] == []
    assert result["trace"]
    assert any(event["step"] == "llm_response" for event in result["trace"])
