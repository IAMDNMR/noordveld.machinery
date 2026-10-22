"""Run one scenario and print what happened: python scripts/run_scenario.py cat_warehouse [more pack ids]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.core.config as config  # noqa: E402

config._load_env_file = lambda *args: None
from app.design_studio.scenarios import run_scenario  # noqa: E402

if __name__ == "__main__":
    ids = sys.argv[1:] or ["cat_warehouse"]
    result = run_scenario("Scenario " + "+".join(ids), ids, "Synthetic scenario for " + ", ".join(ids), keep_files="--keep" in sys.argv)
    print(json.dumps({k: v for k, v in result.items() if k != "ran"}, indent=1, default=str))
    print(f"{len(result['ran'])} actions ran")
    sys.exit(0 if result.get("passed") else 1)
