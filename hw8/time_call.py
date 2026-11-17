#!/usr/bin/env python3
"""Time N real verifier calls end to end (HW8 latency budget). Prints only timings, never the key.

    GEMINI_API_KEY=... python hw8/time_call.py --n 5      # run from the repo root

Each call is one verify() on an eval case: artifact load is done once, then prompt + one Gemini call
(new TCP+TLS connection each time: urllib does not keep connections alive) + parse + threshold.
"""
import argparse, json, os, statistics, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_verify import verifier

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=5)
a = ap.parse_args()
os.environ.pop("AUDIT_LOG", None)
os.environ["LLM_MIN_INTERVAL"] = os.environ.get("LLM_MIN_INTERVAL", "6.5")  # free-tier rate limit; the wait is NOT timed
t0 = time.perf_counter(); m, s = verifier.load(); load_ms = (time.perf_counter() - t0) * 1000
cases = [json.loads(l)["question"] for l in open("eval_set.jsonl", encoding="utf-8")][: a.n]
ts = []
for i, c in enumerate(cases):
    if i:
        time.sleep(float(os.environ["LLM_MIN_INTERVAL"]))
    t = time.perf_counter(); r = verifier.verify(c, m, s); ms = (time.perf_counter() - t) * 1000
    ts.append(ms); print(f"call {i+1}: {ms:7.0f} ms  {r['decision']}  out_tokens={r['usage'].get('output')}")
print(f"artifact load + SHA check: {load_ms:.1f} ms (once per process)")
print(f"end-to-end verify(): median {statistics.median(ts):.0f} ms, max {max(ts):.0f} ms, n={len(ts)}")
