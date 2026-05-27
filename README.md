# CI Fixer Agent

A Claude-powered agent that reads failing CI logs, identifies the root cause, patches the code, and verifies the fix by running pytest.

## How it works

1. Analyse - Claude reads the CI log and source files to identify the root cause
2. Patch - Claude produces a minimal fix targeting only the buggy function
3. Verify - Agent runs pytest in a temp directory to confirm the patch works

## Running locally

pip install -r requirements.txt
set ANTHROPIC_API_KEY=sk-ant-...
python solution.py

## Docker

docker build -t ci-fixer .
docker run --rm -e ANTHROPIC_API_KEY=your_key -v path/to/test_inputs.json:/workspace/test_inputs.json ci-fixer

See decisions.md for architectural choices.
