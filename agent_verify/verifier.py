# -*- coding: utf-8 -*-
"""Agent Verify, layer 2: check an AI agent's output against evidence, policy and the tool registry.

verify(case_text) -> dict with decision, confidence, reason, evidence, raw, usage.
format_line(result) -> "DECISION: BLOCK | confidence 0.91 | reason: ... [E2]"

Everything that can change a decision is pinned in manifest.json: the model snapshot, the prompt
version, the policy version, the tool registry version and the settings (temperature, thresholds).
At load time the file hashes of the prompt, policy and tool registry are checked against the manifest,
so a prompt edit without a version bump fails loudly instead of slipping into a release.
"""
import datetime
import hashlib
import json
import os
import re

from . import llm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISIONS = ("APPROVE", "REVIEW", "BLOCK")


def file_sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]


def artifact_paths(m):
    return {"prompt": os.path.join(ROOT, "prompts", f"verifier_{m['prompt_version']}.txt"),
            "policy": os.path.join(ROOT, "policies", f"policies_{m['policy_version']}.md"),
            "tools": os.path.join(ROOT, "tools", f"tools_{m['tools_version']}.json")}


def load(manifest_path=None):
    m = json.load(open(manifest_path or os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
    paths = artifact_paths(m)
    for name, p in paths.items():
        want = m.get("artifact_sha", {}).get(name)
        got = file_sha(p)
        if want != got:
            raise RuntimeError(f"{name} file {os.path.basename(p)} hashes to {got} but manifest.json says {want}. "
                               "Bump its version (or update artifact_sha) in the same pull request.")
    system = (open(paths["prompt"], encoding="utf-8").read()
              .replace("{POLICY}", open(paths["policy"], encoding="utf-8").read())
              .replace("{TOOLS}", open(paths["tools"], encoding="utf-8").read()))
    return m, system


def _parse(raw):
    match = re.search(r"\{.*\}", raw or "", re.S)
    try:
        obj = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        obj = None
    if not isinstance(obj, dict) or str(obj.get("decision", "")).upper() not in DECISIONS:
        # fail closed: an unreadable verdict is never an approval
        return {"decision": "REVIEW", "confidence": 0.0, "reason": "G3: verifier output was unparseable", "evidence": []}
    try:
        conf = max(0.0, min(1.0, float(obj.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    ev = obj.get("evidence") or []
    ev = [str(e).strip("[] ") for e in (ev if isinstance(ev, list) else [ev]) if str(e).strip()]
    return {"decision": str(obj["decision"]).upper(), "confidence": conf,
            "reason": " ".join(str(obj.get("reason", "")).split()), "evidence": ev}


def verify(case_text, manifest=None, system=None):
    if manifest is None or system is None:
        manifest, system = load()
    s = manifest["settings"]
    raw, usage = llm.complete(manifest["provider"], manifest["model"], system, case_text,
                              s["temperature"], s["max_output_tokens"])
    r = _parse(raw)
    # confidence-aware policy: a low-confidence approval is escalated, never auto-approved
    if r["decision"] == "APPROVE" and r["confidence"] < s["approve_threshold"]:
        r["reason"] = f"confidence {r['confidence']:.2f} below approve threshold {s['approve_threshold']:.2f}; {r['reason']}"
        r["decision"] = "REVIEW"
    r.update(raw=raw, usage=usage)
    audit(case_text, r, manifest)
    return r


def format_line(r):
    cite = r["evidence"][0] if r["evidence"] else "none"
    reason = r["reason"][:240]
    return f"DECISION: {r['decision']} | confidence {r['confidence']:.2f} | reason: {reason} [{cite}]"


def audit(case_text, r, manifest):
    """Append the task, output, confidence, verdict and release to AUDIT_LOG (if set)."""
    path = os.environ.get("AUDIT_LOG")
    if not path:
        return
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "release": manifest["release"], "model": manifest["model"],
           "case_sha": hashlib.sha256(case_text.encode()).hexdigest()[:12],
           "decision": r["decision"], "confidence": r["confidence"], "reason": r["reason"],
           "evidence": r["evidence"], "usage": r["usage"]}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
