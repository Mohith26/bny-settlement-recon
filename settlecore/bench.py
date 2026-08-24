"""Benchmark: capture -> settle throughput and reconciliation timing.

Run with:  python -m settlecore.bench [n_trades] [seed]
Writes results/bench.json with everything it measured.
"""

import json
import platform
import sys
import time

from .engine import SettlementEngine
from .generator import generate_universe, inject_breaks
from .models import TradeState
from .recon import grade_against_labels, reconcile


def run_bench(n_trades=100_000, seed=42):
    results = {
        "n_trades": n_trades,
        "seed": seed,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "platform": platform.platform(),
    }

    t0 = time.perf_counter()
    trades, ledger, opening_cash, opening_positions = generate_universe(
        n_trades, seed
    )
    results["generate_seconds"] = round(time.perf_counter() - t0, 4)

    engine = SettlementEngine(ledger)
    t0 = time.perf_counter()
    settled, failed = engine.run(trades)
    pipeline_seconds = time.perf_counter() - t0
    results["pipeline_seconds"] = round(pipeline_seconds, 4)
    results["trades_per_second"] = round(n_trades / pipeline_seconds, 1)
    results["settled"] = len(settled)
    results["failed"] = len(failed)

    t0 = time.perf_counter()
    report = reconcile(trades, ledger, opening_cash, opening_positions)
    recon_seconds = time.perf_counter() - t0
    results["recon_seconds"] = round(recon_seconds, 4)
    results["clean_recon"] = report.clean
    results["clean_diff_count"] = report.diff_count
    results["clean_break_count"] = len(report.breaks)
    ledger.assert_no_floats()

    # Injected-break run on the same universe.
    labels = inject_breaks(
        ledger,
        settled,
        seed=seed + 1,
        n_missed_settle=25,
        n_wrong_amount=25,
        n_duplicate_posting=25,
    )
    t0 = time.perf_counter()
    dirty = reconcile(trades, ledger, opening_cash, opening_positions)
    results["dirty_recon_seconds"] = round(time.perf_counter() - t0, 4)
    grade = grade_against_labels(dirty, labels)
    results["breaks_injected"] = len(labels)
    results["breaks_detected"] = len(dirty.breaks)
    results["classification_exact_match"] = grade["exact_match"]
    results["detected_counts"] = grade["detected_counts"]
    results["false_positives"] = len(grade["false_positives"])
    results["false_negatives"] = len(grade["false_negatives"])
    return results


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    results = run_bench(n, seed)
    print(json.dumps(results, indent=2))
    with open("results/bench.json", "w") as fh:
        json.dump(results, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
