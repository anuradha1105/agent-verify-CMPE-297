# -*- coding: utf-8 -*-
"""Content hashes for release pinning, with the algorithm chosen in manifest.json ("hash_alg").

Crypto-agility (CMPE 297 Homework 7): the algorithm used to pin the prompt, policy and tool files and the
eval set used to be hard-coded as SHA-256 in two places. It is now one manifest setting, so moving to
another hash is a configuration change plus re-pinning, not a code change. Only algorithms on the
allow-list are accepted; MD5 and SHA-1 are refused on purpose.
"""
import hashlib

DEFAULT = "sha256"
ALLOWED = ("sha256", "sha384", "sha512", "sha3_256", "sha3_384", "sha3_512", "blake2b")
LENGTH = 12   # hex characters kept in manifest.json; unchanged from the original pins


def alg_of(manifest):
    alg = str((manifest or {}).get("hash_alg", DEFAULT)).lower().replace("-", "_")
    if alg not in ALLOWED:
        raise ValueError(f"manifest.json hash_alg {alg!r} is not allowed; use one of {', '.join(ALLOWED)}")
    return alg


def digest(data, alg=DEFAULT):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.new(alg, data).hexdigest()[:LENGTH]
