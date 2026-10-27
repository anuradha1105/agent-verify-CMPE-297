# Agent Verify

Confidence-aware verification for enterprise AI agents. CMPE 297, Fall 2026: Jay Vithlani, Yash Kalathiya,
Anuradha Srivastav.

A task-performing agent produces an output (approve this vendor, run this remediation, call this tool).
Agent Verify checks that output against the evidence, the policy (`policies/`) and the tool registry
(`tools/`) before anything acts on it, and returns one of:

    DECISION: APPROVE | confidence 0.93 | reason: V1-V4 satisfied ... [E1]
    DECISION: REVIEW  | confidence 0.81 | reason: V2: DPA not signed ... [E2]
    DECISION: BLOCK   | confidence 0.95 | reason: I2: destructive prod action without ticket [E3]

An APPROVE below `approve_threshold` (manifest settings) is escalated to REVIEW. Every verdict can be
written to an audit log (`AUDIT_LOG=audit_log.jsonl`).

## Layout

| Path | What it is |
|---|---|
| `agent_verify/verifier.py` | the verification layer: prompt + policy + tools, one LLM call, threshold, audit |
| `agent_verify/llm.py` | stdlib client for OpenAI and Gemini; key from the environment |
| `prompts/`, `policies/`, `tools/` | versioned artifacts; their file hashes are pinned in `manifest.json` |
| `manifest.json` | the release: model snapshot, versions, settings, eval set hash, gate rule |
| `eval_set.jsonl` | 32 cases: approve 10, review 10, block 8, critical 4 |
| `eval_gate.py` | course starter gate (unchanged) |
| `system.py` | adapter: `answer(case)` -> verdict line |
| `.github/workflows/eval-gate.yml` | gate on every pull request |
| `.github/workflows/baseline.yml` | manual A/A run; commits `baseline.json` and its output to main |

No dependencies: Python 3.10+ standard library only.

## Run

    export OPENAI_API_KEY=...            # or GEMINI_API_KEY, with "provider": "gemini" in manifest.json
    python verify.py < some_case.txt      # one verdict
    python eval_gate.py --hash            # eval set hash
    python eval_gate.py --aa              # noise floor, writes baseline.json
    python eval_gate.py --gate            # SHIP or BLOCK against baseline.json

On the Gemini free tier set `LLM_MIN_INTERVAL=6.5` (repository variable in CI) to stay under the rate limit.

## Release rules

- Changing a prompt, policy or tool file means a new version file and a manifest bump; the verifier
  refuses to load if a file's hash does not match `artifact_sha`.
- Changing `eval_set.jsonl` means updating `eval_set_hash` in the same pull request, then re-running the
  baseline workflow on main.
- A test case is never edited to make a release pass.
- Keys live in repository secrets only.
