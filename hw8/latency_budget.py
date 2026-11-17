#!/usr/bin/env python3
"""Add up a latency budget and compare it with a deadline. CMPE 297 Homework 8 starter.

The budget is a CSV with columns component,ms,source. Use a measured number where you have one (the source
says how you measured it) and an estimate where you do not (the source says "estimate" and why).
A component may instead give a distance: put km in the ms column as e.g. "km:1100" and the script converts
it to a fibre round trip (2 x km x 1.5 path stretch / 200 km per ms).

    python latency_budget.py budget_example.csv --deadline 800
"""
import argparse
import csv
import sys

FIBRE_KM_PER_MS = 200.0
PATH_STRETCH = 1.5


def fibre_rtt_ms(km):
    return 2 * float(km) * PATH_STRETCH / FIBRE_KM_PER_MS


def load(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        v = r["ms"].strip()
        if v.lower().startswith("km:"):
            ms = fibre_rtt_ms(v.split(":", 1)[1])
            r["source"] = (r.get("source") or "") + f" [fibre round trip for {v[3:]} km]"
        else:
            ms = float(v)
        if ms < 0:
            raise SystemExit(f"{r['component']}: negative time")
        rows.append({"component": r["component"].strip(), "ms": ms, "source": (r.get("source") or "").strip()})
    return rows


def report(rows, deadline):
    total = sum(r["ms"] for r in rows)
    print(f"{'component':<38} {'ms':>9}  share  source")
    for r in rows:
        print(f"{r['component']:<38} {r['ms']:>9.1f}  {r['ms'] / total:>5.0%}  {r['source']}")
    print(f"{'TOTAL':<38} {total:>9.1f}")
    verdict = "MEETS" if total <= deadline else "MISSES"
    print(f"deadline {deadline:g} ms: {verdict} it by {abs(deadline - total):.1f} ms")
    biggest = max(rows, key=lambda r: r["ms"])
    print(f"largest component: {biggest['component']} ({biggest['ms']:.1f} ms). Start there.")
    unsourced = [r["component"] for r in rows if not r["source"]]
    if unsourced:
        print("WARNING: no source given for: " + ", ".join(unsourced))
    return total, verdict


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("budget")
    ap.add_argument("--deadline", type=float, required=True, help="ms")
    a = ap.parse_args(argv)
    return report(load(a.budget), a.deadline)


if __name__ == "__main__":
    total, verdict = main()
    sys.exit(0 if verdict == "MEETS" else 1)
