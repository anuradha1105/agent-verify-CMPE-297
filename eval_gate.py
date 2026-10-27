# -*- coding: utf-8 -*-
"""CMPE 297 Homework 6 starter: an eval gate for a generative system. Standard library only.

Three commands, run from the repository root:

    python eval_gate.py --aa       # measure the noise floor: run the current system against itself,
                                   # write baseline.json (means and sigma per category)
    python eval_gate.py --gate     # run the current system, compare with baseline.json, exit 1 to block
    python eval_gate.py --hash     # print the eval set's content hash (paste it into manifest.json)

What it reads:
    manifest.json      every versioned artifact of the release, and the gate rule
    eval_set.jsonl     one test case per line: id, category, question, checks
    system.py          your adapter: a function answer(question) -> str that calls YOUR system

Check kinds a test case may use:
    ["contains", "text"]     the answer contains this text (case-insensitive)
    ["not_contains", "text"] the answer does not contain it
    ["cites", "ID"]          the answer ends with [ID]
    ["refuses", ""]          the answer says it does not have the information
    ["regex", "pattern"]     the answer matches this regular expression
"""
import argparse
import hashlib
import importlib
import json
import math
import os
import re
import statistics
import sys

HERE = os.getcwd()
REFUSAL = re.compile(r"do not have that information|cannot answer|not in the (catalog|documents|context)", re.I)


def load_cases(path="eval_set.jsonl"):
    cases = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        sys.exit("eval set has duplicate ids; the gate would compare the wrong cases")
    return cases


def eval_set_hash(cases):
    canon = json.dumps(sorted(cases, key=lambda c: c["id"]), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canon.encode()).hexdigest()[:12]


def check(answer, kind, arg):
    a = answer or ""
    if kind == "contains":
        return arg.lower() in a.lower()
    if kind == "not_contains":
        return arg.lower() not in a.lower()
    if kind == "cites":
        return a.rstrip().endswith(f"[{arg}]")
    if kind == "refuses":
        return bool(REFUSAL.search(a))
    if kind == "regex":
        return re.search(arg, a) is not None
    raise ValueError(f"unknown check kind {kind!r}")


def run_once(system, cases, run):
    rows = {}
    for c in cases:
        try:
            a = system.answer(c["question"], seed=run) if "seed" in system.answer.__code__.co_varnames else system.answer(c["question"])
            err = None
        except Exception as e:          # an error is a failed case, not a crashed gate
            a, err = "", f"{type(e).__name__}: {e}"
        ok = err is None and all(check(a, k, v) for k, v in c["checks"])
        rows[c["id"]] = {"pass": ok, "tokens": max(1, round(len(a) / 4)), "error": err}
    return rows


def summarise(rows, cases):
    by = {}
    for c in cases:
        by.setdefault(c["category"], []).append(rows[c["id"]]["pass"])
    s = {k: sum(v) / len(v) for k, v in by.items()}
    s["overall"] = sum(r["pass"] for r in rows.values()) / len(rows)
    s["tokens"] = statistics.mean(r["tokens"] for r in rows.values())
    return s


def runs(system, cases, n, offset=0):
    return [summarise(run_once(system, cases, offset + i), cases) for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--aa", action="store_true")
    g.add_argument("--gate", action="store_true")
    g.add_argument("--hash", action="store_true")
    ap.add_argument("--aa-runs", type=int, default=10)
    args = ap.parse_args()

    cases = load_cases()
    h = eval_set_hash(cases)
    if args.hash:
        print(h)
        return 0
    manifest = json.load(open("manifest.json", encoding="utf-8"))
    if manifest.get("eval_set_hash") != h:
        print(f"BLOCK: manifest.json says eval set {manifest.get('eval_set_hash')}, the file hashes to {h}. "
              "Update the manifest in the same pull request as the eval set.")
        return 1
    rule = manifest["gate"]
    R = int(rule.get("runs", 5))
    sys.path.insert(0, HERE)
    system = importlib.import_module(manifest.get("adapter", "system"))
    cats = sorted({c["category"] for c in cases}) + ["overall"]

    if args.aa:
        ss = runs(system, cases, args.aa_runs)
        base = {k: statistics.mean(s[k] for s in ss) for k in cats + ["tokens"]}
        sd = {k: statistics.pstdev([s[k] for s in ss]) for k in cats}
        sigma = {k: sd[k] * math.sqrt(2 / R) for k in cats}
        out = {"manifest": manifest, "eval_set_hash": h, "aa_runs": args.aa_runs, "runs_per_comparison": R,
               "mean": base, "run_sd": sd, "sigma": sigma}
        json.dump(out, open("baseline.json", "w", encoding="utf-8"), indent=1)
        lo, hi = min(s["overall"] for s in ss), max(s["overall"] for s in ss)
        print(f"A/A: {args.aa_runs} runs of the same release, overall {lo:.1%} to {hi:.1%}")
        for k in cats:
            print(f"  {k:12} mean {base[k]:6.1%}   sd of one run {sd[k]:5.1%}   sigma of a {R}-run comparison {sigma[k]:5.1%}")
        print("wrote baseline.json. Commit it with the release it measured.")
        return 0

    if not os.path.exists("baseline.json"):
        print("BLOCK: no baseline.json. Run `python eval_gate.py --aa` on the production release first.")
        return 1
    b = json.load(open("baseline.json", encoding="utf-8"))
    if b["eval_set_hash"] != h:
        print(f"NOTE: the baseline was measured on eval set {b['eval_set_hash']}, this run uses {h}. "
              "Re-measure the baseline on production with the new eval set before you trust the comparison.")
    ss = runs(system, cases, R, offset=1000)
    cand = {k: statistics.mean(s[k] for s in ss) for k in cats + ["tokens"]}
    reasons = []
    for k in rule.get("critical", []):
        if k in cats and min(s[k] for s in ss) < 1.0:
            reasons.append(f"critical category {k} failed a case")
    for k in cats:
        drop = b["mean"].get(k, 0) - cand[k]
        sig = b["sigma"].get(k, 0)
        if sig > 0 and drop > float(rule["max_drop_sigma"]) * sig:
            reasons.append(f"{k} fell {drop:.1%}, {drop / sig:.1f} sigma (limit {rule['max_drop_sigma']})")
        elif sig == 0 and drop > 0 and k not in rule.get("critical", []):
            reasons.append(f"{k} fell {drop:.1%} and its A/A sigma is 0: re-measure the baseline")
    rise = cand["tokens"] / b["mean"]["tokens"] - 1
    if rise > float(rule["max_token_increase"]):
        reasons.append(f"tokens per answer rose {rise:.0%} (limit {float(rule['max_token_increase']):.0%})")
    verdict = "BLOCK" if reasons else "SHIP"
    report = {"verdict": verdict, "reasons": reasons, "manifest": manifest, "eval_set_hash": h,
              "baseline": b["mean"], "candidate": cand}
    json.dump(report, open("gate_report.json", "w", encoding="utf-8"), indent=1)
    print(f"{verdict}: candidate vs baseline, {R} runs each, eval set {h}")
    for k in cats:
        sig = b["sigma"].get(k, 0)
        z = f"{(cand[k] - b['mean'][k]) / sig:+.1f} sigma" if sig else "   n/a"
        print(f"  {k:12} {b['mean'][k]:6.1%} -> {cand[k]:6.1%}   {z}")
    print(f"  tokens       {b['mean']['tokens']:6.1f} -> {cand['tokens']:6.1f}   {rise:+.0%}")
    for r in reasons:
        print("  -", r)
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
