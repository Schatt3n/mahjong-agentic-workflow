from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_badcase_regression_coverage.py"


def load_checker_module():
    spec = importlib.util.spec_from_file_location("check_badcase_regression_coverage", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fixed_badcases_have_verified_regression_refs() -> None:
    module = load_checker_module()

    fixed, skipped, errors = module.audit_badcases()

    assert fixed > 0
    assert skipped >= 0
    assert errors == []
