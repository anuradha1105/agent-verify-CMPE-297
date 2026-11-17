#!/usr/bin/env python3
"""Measure round trips to the endpoints your project depends on. CMPE 297 Homework 8 starter.

It times the TCP connection (one round trip: SYN, SYN-ACK) and, for port 443, the TLS handshake on top
(usually one more round trip). Standard library only. Run it from where your users are, and from where your
code runs, and keep both results.

    python rtt_probe.py api.openai.com:443 your-app.example.com:443 --count 20
    python rtt_probe.py --file endpoints.txt --count 20 --csv rtt.csv

Each endpoint is host:port. Lines in --file starting with # are ignored. Nothing is sent after the
handshake: no request, no credentials.
"""
import argparse
import csv
import socket
import ssl
import statistics
import sys
import time


def probe(host, port, timeout=5.0, tls=None):
    """One measurement: (tcp_ms, tls_ms or None). Raises OSError on failure."""
    t0 = time.perf_counter()
    sock = socket.create_connection((host, port), timeout=timeout)
    t1 = time.perf_counter()
    tls_ms = None
    try:
        if tls is None:
            tls = port == 443
        if tls:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(sock, server_hostname=host) as s:
                t2 = time.perf_counter()
                tls_ms = (t2 - t1) * 1000
                sock = None
    finally:
        if sock is not None:
            sock.close()
    return (t1 - t0) * 1000, tls_ms


def percentile(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def measure(endpoint, count=10, pause=0.2, timeout=5.0, tls=None):
    host, _, port = endpoint.rpartition(":")
    if not host:
        raise SystemExit(f"{endpoint!r}: write it as host:port")
    port = int(port)
    tcp, tl, errors = [], [], []
    for _ in range(count):
        try:
            a, b = probe(host, port, timeout=timeout, tls=tls)
            tcp.append(a)
            if b is not None:
                tl.append(b)
        except OSError as e:
            errors.append(f"{type(e).__name__}: {e}")
        time.sleep(pause)
    row = {"endpoint": endpoint, "ok": len(tcp), "failed": len(errors),
           "tcp_median_ms": round(statistics.median(tcp), 2) if tcp else None,
           "tcp_p95_ms": round(percentile(tcp, 0.95), 2) if tcp else None,
           "tls_median_ms": round(statistics.median(tl), 2) if tl else None,
           "first_error": errors[0] if errors else ""}
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("endpoints", nargs="*", help="host:port")
    ap.add_argument("--file", help="one host:port per line")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--no-tls", action="store_true", help="time only the TCP connection, even on 443")
    ap.add_argument("--csv", help="also write the results here")
    a = ap.parse_args(argv)
    eps = list(a.endpoints)
    if a.file:
        eps += [ln.strip() for ln in open(a.file, encoding="utf-8") if ln.strip() and not ln.lstrip().startswith("#")]
    if not eps:
        ap.error("give at least one host:port")
    rows = [measure(e, a.count, timeout=a.timeout, tls=(False if a.no_tls else None)) for e in eps]
    print(f"{'endpoint':<40} {'ok':>3} {'fail':>4} {'tcp median':>11} {'tcp p95':>9} {'tls median':>11}")
    for r in rows:
        f = lambda v: "-" if v is None else f"{v:.1f}"
        print(f"{r['endpoint']:<40} {r['ok']:>3} {r['failed']:>4} {f(r['tcp_median_ms']):>11} {f(r['tcp_p95_ms']):>9} "
              f"{f(r['tls_median_ms']):>11}" + (f"   ({r['first_error']})" if r["first_error"] else ""))
    print("\nms. The TCP connection is one round trip; a TLS 1.3 handshake is usually one more.")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("wrote", a.csv)
    return rows


if __name__ == "__main__":
    main()
    sys.exit(0)
