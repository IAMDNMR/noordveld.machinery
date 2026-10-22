"""Generate the application for each evaluation scenario and run the generated application's own tests.
Usage: python scripts/evaluate_runtime.py [scenario-substring]"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.design_studio.compiler import compile_project
from app.design_studio.evaluation import SCENARIOS, build, with_evaluation_approval
from app.design_studio.knowledge.provider import LocalKnowledgeProvider
from app.domain_knowledge.store import ReadOnlyDomainStore


def run_one(name: str, packs: list[str]) -> dict:
    definition = with_evaluation_approval(build(packs))
    compiled = compile_project(definition, ReadOnlyDomainStore(), LocalKnowledgeProvider())
    out = {"name": name, "status": compiled["status"], "reasons": compiled["plan"].get("reasons", []) if isinstance(compiled["plan"], dict) else []}
    if compiled["status"] != "generated":
        return out
    with tempfile.TemporaryDirectory(prefix="noordveld-eval-") as directory:
        root = Path(directory)
        for path, content in compiled["files"].items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "runtime", "-p", "test_runtime.py", "-v"],
            cwd=root, capture_output=True, text=True, timeout=600,
        )
        text = result.stdout + result.stderr
        out["tests"] = {
            "ran": int((re.search(r"Ran (\d+) test", text) or [0, 0])[1]),
            "failed": len(re.findall(r"\.\.\. (?:FAIL|ERROR)\b", text)),
            "skipped": len(re.findall(r"\.\.\. skipped", text)),
        }
        out["failures"] = re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M)[:8]
        out["skips"] = sorted(set(re.findall(r"skipped '([^']+)'", text)))[:6]
        out["tail"] = text.strip().splitlines()[-1:]
        out["log"] = text
    return out


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    bad = 0
    for name, packs in SCENARIOS.items():
        if only and only not in name:
            continue
        result = run_one(name, packs)
        tests = result.get("tests")
        ok = result["status"] == "generated" and tests and not tests["failed"]
        print(f"\n{'PASS' if ok else 'FAIL'}  {name}: generation {result['status']}" + (f", {tests['ran']} ran, {tests['failed']} failed, {tests['skipped']} skipped" if tests else ""))
        for reason in result.get("reasons", [])[:4]:
            print("    blocked:", reason)
        for failure in result.get("failures", []):
            print("    failed:", failure)
        for skip in result.get("skips", []):
            print("    skipped:", skip)
        bad += not ok
    print(f"\n{bad} scenario(s) with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
