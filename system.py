# -*- coding: utf-8 -*-
"""Adapter between eval_gate.py and Agent Verify. answer(question) gets one eval case (the task, the
agent's output and the evidence, as text) and returns the verifier's one-line verdict."""
from agent_verify import verifier

MANIFEST, SYSTEM_PROMPT = verifier.load()


def answer(question):
    return verifier.format_line(verifier.verify(question, MANIFEST, SYSTEM_PROMPT))
