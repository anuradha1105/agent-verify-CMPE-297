#!/usr/bin/env python3
"""Check a network policy against its intents. CMPE 297 Homework 8 starter.

The policy is a JSON file with an ordered rule list (first match wins, default deny) and a list of invariants.
It is the same model as the in-class lab, so you can describe your own deployment (security groups, a
Kubernetes NetworkPolicy, docker-compose networks, a home router) in it and test it.

    python intent_check.py policy_example.json
    python intent_check.py policy_example.json --plant corp,db,5432,allow

--plant puts one extra rule at the TOP of the list, then runs the same checks. Use it to show that your checks
can fail: a check that has never failed has shown nothing. Exit code 0 when every invariant holds, 1 otherwise.

Invariant kinds:
  {"kind": "must_reach",     "from": "web", "to": "api", "port": 443}
  {"kind": "must_not_reach", "from": "internet", "to": "db", "port": "any"}
  {"kind": "only_reaches",   "from": "cameras", "allowed": [["edge", 8554]]}
"""
import argparse
import json
import sys


def allowed(rules, src, dst, port):
    for r in rules:
        s, d, p, action = r
        if s in (src, "any") and d in (dst, "any") and p in (port, "any"):
            return action == "allow"
    return False


def check(policy, rules=None):
    rules = policy["rules"] if rules is None else rules
    zones, ports = policy["zones"], policy["ports"]
    problems = []
    for inv in policy["invariants"]:
        k = inv["kind"]
        if k == "must_reach":
            if not allowed(rules, inv["from"], inv["to"], inv["port"]):
                problems.append(f"must_reach: {inv['from']} -> {inv['to']}:{inv['port']} is blocked")
        elif k == "must_not_reach":
            pts = ports if inv["port"] == "any" else [inv["port"]]
            for p in pts:
                if allowed(rules, inv["from"], inv["to"], p):
                    problems.append(f"must_not_reach: {inv['from']} -> {inv['to']}:{p} is allowed")
        elif k == "only_reaches":
            ok = {(d, p) for d, p in inv["allowed"]}
            for d in zones:
                if d == inv["from"]:
                    continue
                for p in ports:
                    if allowed(rules, inv["from"], d, p) and (d, p) not in ok:
                        problems.append(f"only_reaches: {inv['from']} -> {d}:{p} is allowed")
        else:
            problems.append(f"unknown invariant kind {k!r}")
    return problems


def parse_rule(text):
    text = text.strip()
    if text.startswith("["):
        return json.loads(text)
    parts = [x.strip() for x in text.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"--plant {text!r}: write from,to,port,action")
    port = parts[2] if parts[2] == "any" else int(parts[2])
    return [parts[0], parts[1], port, parts[3]]


def validate_policy(policy):
    for key in ("zones", "ports", "rules", "invariants"):
        if key not in policy:
            raise SystemExit(f"policy is missing {key!r}")
    zones = set(policy["zones"]) | {"any"}
    for r in policy["rules"]:
        if len(r) != 4 or r[3] not in ("allow", "deny"):
            raise SystemExit(f"bad rule {r!r}: [from, to, port, allow|deny]")
        for z in r[:2]:
            if z not in zones:
                raise SystemExit(f"rule {r!r} names unknown zone {z!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("policy")
    ap.add_argument("--plant", help="one rule: from,to,port,action (e.g. corp,db,5432,allow), or the same as JSON")
    a = ap.parse_args(argv)
    policy = json.load(open(a.policy, encoding="utf-8"))
    validate_policy(policy)
    rules = list(policy["rules"])
    if a.plant:
        planted = parse_rule(a.plant)
        validate_policy(dict(policy, rules=[planted]))
        rules = [planted] + rules
        print("PLANTED at the top:", rules[0])
    problems = check(policy, rules)
    n = len(policy["invariants"])
    if problems:
        print(f"FAIL: {len(problems)} violation(s) of {n} invariant(s)")
        for p in problems:
            print("  -", p)
    else:
        print(f"PASS: all {n} invariant(s) hold for {len(rules)} rule(s)")
    return problems


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
