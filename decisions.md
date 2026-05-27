# Key Decisions

## 1. Four-stage agent loop (analyse log -> inspect code -> patch -> verify)
The agent separates CI log analysis, code inspection, patching, and verification into distinct steps. A single Claude call handles the first three stages, followed by an actual pytest run for verification. This matches the rubric architecture requirement and ensures CI evidence drives the fix.

## 2. CI log as primary evidence
The prompt foregrounds the failing CI log with actual vs expected values before showing source files. This forces the model to reason from the error signal outward to the root cause rather than doing a broad code review that might miss the specific failure.

## 3. Actual pytest verification in a temp directory
After Claude produces the patch, the agent writes all files to a temporary directory and runs pytest via subprocess. The verification result is included in the response, catching cases where the patch compiles but still fails the test.

## 4. Minimal patch principle
The prompt asks for the smallest change that fixes the failing test without rewriting unrelated code. For the percentage discount bug this means only changing the formula from price * percent to price * percent / 100 in the single affected function.

## 5. Graceful degradation per item
Each CI case is processed in an independent try/except block. If Claude or pytest fails an error entry is written and processing continues so results.json always has one entry per input.
