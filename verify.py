# -*- coding: utf-8 -*-
"""Command line demo: python verify.py case.txt   (or pipe a case on stdin)

A case is plain text with SCENARIO, TASK, AGENT OUTPUT and EVIDENCE sections; see eval_set.jsonl.
"""
import json
import sys

from agent_verify import verifier

text = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
r = verifier.verify(text)
print(verifier.format_line(r))
print(json.dumps({k: r[k] for k in ("decision", "confidence", "evidence", "usage")}, indent=1))
