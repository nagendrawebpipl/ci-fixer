#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import anthropic

TEST_INPUTS_PATH = Path(os.environ.get("TEST_INPUTS_PATH", "test_inputs.json"))
RESULTS_PATH     = Path(os.environ.get("RESULTS_PATH",     "results.json"))

ANALYSE_PROMPT = (
    "You are an expert CI debugging agent.\n"
    "A Python repository has a failing test. Analyse the CI log and source files to identify the root cause.\n\n"
    "## Failing CI log\n{ci_log}\n\n"
    "## Repository files\n{repo_files}\n\n"
    "Think step by step:\n"
    "1. What does the CI log tell you about the actual vs expected values?\n"
    "2. Which file and function contains the bug?\n"
    "3. What is the exact root cause (wrong formula, off-by-one, wrong operator, etc.)?\n\n"
    "Respond ONLY with a JSON object, no markdown fences:\n"
    '{{"failing_test": "<test name>", "failing_file": "<file>", "failing_function": "<function>", '
    '"root_cause": "<one sentence>", "fix_description": "<one sentence>", '
    '"patched_files": [{{"path": "<filename>", "content": "<full corrected content>"}}], '
    '"verification_note": "<one sentence>"}}'
)

def _call(client, prompt, retries=3):
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except (json.JSONDecodeError, anthropic.APIError) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Claude failed: {exc}") from exc

def format_files(repo_files):
    parts = []
    for f in repo_files:
        parts.append(f"### {f['path']}\n{f['content']}")
    return "\n\n".join(parts)

def verify_patch(repo_files, patched_files):
    file_map = {f["path"]: f["content"] for f in repo_files}
    for pf in patched_files:
        file_map[pf["path"]] = pf["content"]
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for path, content in file_map.items():
            (tmp / path).write_text(content)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", "--tb=short"],
                cwd=tmpdir, capture_output=True, text=True, timeout=30,
            )
            passed = result.returncode == 0
            output = (result.stdout + result.stderr).strip()
        except subprocess.TimeoutExpired:
            passed = False
            output = "pytest timed out after 30s"
        except Exception as exc:
            passed = False
            output = str(exc)
    return {"passed": passed, "output": output[-1000:]}

def process_item(client, item):
    inp        = item.get("input", item)
    repo_files = inp.get("repository_files", [])
    ci_log     = inp.get("failing_ci_log", "")
    prompt     = ANALYSE_PROMPT.format(ci_log=ci_log, repo_files=format_files(repo_files))
    analysis   = _call(client, prompt)
    patched_files   = analysis.get("patched_files", [])
    root_cause      = analysis.get("root_cause", "")
    fix_description = analysis.get("fix_description", "")
    verification    = verify_patch(repo_files, patched_files)
    return {
        "id": item["id"],
        "output": {
            "failing_file":     analysis.get("failing_file", ""),
            "failing_function": analysis.get("failing_function", ""),
            "root_cause":       root_cause,
            "fix_description":  fix_description,
            "patched_files":    patched_files,
            "verification": {
                "passed": verification["passed"],
                "output": verification["output"],
            },
            "report": (
                f"FAILURE: {ci_log}\n"
                f"ROOT CAUSE: {root_cause}\n"
                f"FIX: {fix_description}\n"
                f"VERIFIED: {'PASS' if verification['passed'] else 'FAIL'}"
            ),
        },
    }

def main():
    if not TEST_INPUTS_PATH.exists():
        print(f"ERROR: {TEST_INPUTS_PATH} not found", file=sys.stderr)
        sys.exit(1)
    test_inputs = json.loads(TEST_INPUTS_PATH.read_text())
    client      = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    results     = []
    total       = len(test_inputs)
    for idx, item in enumerate(test_inputs, 1):
        print(f"[{idx}/{total}] Fixing {item['id']} ...")
        try:
            result = process_item(client, item)
            results.append(result)
            verified = result["output"]["verification"]["passed"]
            status   = "PASS" if verified else "FAIL"
            print(f"  {status} - {result['output']['root_cause'][:60]}")
        except Exception as exc:
            print(f"  Error: {exc}", file=sys.stderr)
            results.append({
                "id": item["id"],
                "output": {
                    "failing_file": "",
                    "failing_function": "",
                    "root_cause": f"ERROR: {exc}",
                    "fix_description": "",
                    "patched_files": [],
                    "verification": {"passed": False, "output": str(exc)},
                    "report": f"ERROR: {exc}",
                },
            })
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    passed = sum(1 for r in results if r["output"]["verification"].get("passed"))
    print(f"\nDone - {passed}/{len(results)} verified, written to {RESULTS_PATH}")

if __name__ == "__main__":
    main()

