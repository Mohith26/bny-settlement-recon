# Benchmark and validation notes

All numbers below are from runs I executed on my own machine: Apple silicon (arm64), macOS, Python 3.9.6, single thread. Timings use `time.perf_counter()`. Raw JSON is committed under `results/`.

## Setup

```
cd bny-settlement-recon
python3 -m venv .venv && .venv/bin/pip install -U pip pytest pytest-cov
```

## Throughput and reconciliation

Command:

```
.venv/bin/python -m settlecore.bench 100000 42
```

Output is printed and written to `results/bench.json`. From my run:

| Metric | 100k trades | 500k trades |
| --- | --- | --- |
| generate_seconds | 0.2853 | 1.4207 |
| pipeline_seconds (capture to settle, incl. retries) | 0.456 | 2.2559 |
| trades_per_second | 219,285 | 221,641 |
| settled / failed | 99,514 / 486 | 498,020 / 1,980 |
| clean recon time (s) | 0.1228 | 0.6522 |
| clean recon diffs | 0 | 0 |

The 500k run was produced with the same `run_bench` function at `n=500000, seed=42` and saved to `results/bench_500k.json`:

```
.venv/bin/python -c "import json; from settlecore.bench import run_bench; r=run_bench(500000,42); print(json.dumps(r,indent=2))"
```

The failed trades are genuine insufficient-cash or insufficient-shares fails that survived every retry pass in that seeded universe; reconciliation correctly ignores unsettled trades and still comes out to zero differences.

## Break detection and classification

Both bench runs inject 75 labelled breaks into the live ledger after the clean recon: 25 missed settles, 25 wrong amounts, 25 duplicate postings. In both the 100k and 500k runs:

- breaks detected: 75 of 75
- classification exact match against ground-truth labels: true
- false positives: 0, false negatives: 0
- detected counts by class: 25 / 25 / 25

The wrong-amount injections are kept double-entry balanced on purpose, so they are invisible to a totals-level check and only fall out of the per-trade journal comparison.

## Tests and coverage

```
.venv/bin/pytest --color=no -q --cov=settlecore --cov-report=term
```

From my run: **99 passed** in about 1.0 s. Coverage 98% overall (every module at 100% except `settlecore/bench.py` at 84%, whose CLI `main()` is exercised manually rather than under pytest).

Highlights of what the suite pins down:

- the full 25-pair transition matrix (5 legal moves succeed, 20 illegal moves raise, state unchanged on rejection)
- integer-money enforcement at every entry point (floats, bools, strings, None all rejected; `assert_no_floats` catches a corrupted balance)
- double-entry rejection of unbalanced cash and position entries before any balance moves
- DvP atomicity, both fail reasons, retry after funding arrives, and a two-trade ordering case cured by a retry pass
- property-style runs: 8 random interleavings of 1,000 trades all reconcile to zero diffs, cash and share conservation across shuffles, and a stepwise interleaved lifecycle run
- end-to-end determinism: same seed gives identical states and balances, different seeds differ
- each break type detected and classified exactly, a mixed 18-break run graded exactly, and the exact cent skew of a wrong-amount break showing up in the balance diffs

## Caveats

Timings are single runs, not averaged over repetitions, so expect a few percent of run-to-run noise. Everything is single-threaded pure Python; the numbers say nothing about a compiled or concurrent implementation. The trade universe is uniform random over 20 accounts and 10 securities with generous opening balances, which is friendlier than real flow.
