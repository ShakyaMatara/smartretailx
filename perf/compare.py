#!/usr/bin/env python3
"""Build the scalability comparison chart and table from Locust CSV output.

Usage:  python perf/compare.py
"""
import csv
import sys
from pathlib import Path

RESULTS = Path("perf/results")


def read_stats(path):
    if not path.exists():
        sys.exit(f"missing {path} — run the scaling script first")
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return {r["Name"]: r for r in rows}


def num(row, key):
    try:
        return float(row.get(key, 0) or 0)
    except ValueError:
        return 0.0


def main():
    one = read_stats(RESULTS / "05-scale-1x_stats.csv")
    three = read_stats(RESULTS / "06-scale-3x_stats.csv")

    a, b = one.get("Aggregated"), three.get("Aggregated")
    if not a or not b:
        sys.exit("no Aggregated row found in the CSV output")

    metrics = [
        ("Requests", "Request Count", "{:.0f}"),
        ("Failures", "Failure Count", "{:.0f}"),
        ("Throughput (req/s)", "Requests/s", "{:.1f}"),
        ("Median (ms)", "Median Response Time", "{:.0f}"),
        ("p95 (ms)", "95%", "{:.0f}"),
        ("p99 (ms)", "99%", "{:.0f}"),
        ("Max (ms)", "Max Response Time", "{:.0f}"),
    ]

    print()
    print(f"{'Metric':<22}{'1 instance':>14}{'3 instances':>14}{'Change':>12}")
    print("-" * 62)
    for label, key, fmt in metrics:
        va, vb = num(a, key), num(b, key)
        if va:
            delta = (vb - va) / va * 100
            change = f"{delta:+.1f}%"
        else:
            change = "n/a"
        print(f"{label:<22}{fmt.format(va):>14}{fmt.format(vb):>14}{change:>12}")

    err_a = num(a, "Failure Count") / max(num(a, "Request Count"), 1) * 100
    err_b = num(b, "Failure Count") / max(num(b, "Request Count"), 1) * 100
    print(f"{'Error rate':<22}{err_a:>13.2f}%{err_b:>13.2f}%")
    print()

    # Per-endpoint p95, which is where the bottleneck usually shows.
    print(f"{'Endpoint':<32}{'p95 1x':>10}{'p95 3x':>10}{'Change':>12}")
    print("-" * 64)
    for name in sorted(set(one) | set(three)):
        if name in ("Aggregated", ""):
            continue
        ra, rb = one.get(name), three.get(name)
        if not ra or not rb:
            continue
        pa, pb = num(ra, "95%"), num(rb, "95%")
        change = f"{(pb - pa) / pa * 100:+.1f}%" if pa else "n/a"
        print(f"{name[:31]:<32}{pa:>10.0f}{pb:>10.0f}{change:>12}")
    print()


if __name__ == "__main__":
    main()
