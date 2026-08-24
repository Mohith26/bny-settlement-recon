# SettleCore

I wanted to understand what actually happens to a trade after it is executed, so I built a small custody-style post-trade system from scratch: trade capture, a settlement lifecycle state machine, delivery-versus-payment bookkeeping over double-entry ledgers, and a reconciliation engine that proves the books are right to the cent and names the exact trade and failure mode when they are not.

Everything is plain Python 3.9 with no runtime dependencies. Money never touches a float anywhere in the system.

## How a trade flows through it

```
capture -> pending -> matched -> affirmed -> settled
                                    |          ^
                                    v          |
                                  failed ------+   (retry)
```

1. **Capture** validates the raw trade: positive quantity, positive integer-cent price, buyer is not the seller. Bad trades are rejected before they ever get a state.
2. **Lifecycle** is enforced by a hard state machine. There are exactly five legal transitions out of the 25 possible ordered state pairs, and anything else raises `IllegalTransitionError` with the trade id and both states in the message. The test suite walks the entire 25-pair matrix.
3. **Settlement** is DvP: the cash entry and the share entry post together or not at all. If the buyer lacks cash or the seller lacks shares, the trade moves to `failed` with a specific reason, and the engine retries failed trades in later passes, since one account's settlement often frees up the cash another trade was waiting on. Retrying stops when a pass makes no progress.
4. **Ledgers** are double-entry: every cash journal entry's legs must net to zero cents and every position entry's legs must net to zero shares, or the posting is rejected before any balance moves. Every posting is tagged with the trade id that caused it.

## The reconciliation engine

The recon never trusts the ledger. It rebuilds an independent statement from opening balances plus the settled portion of the trade log, then:

- compares expected cash per account and expected shares per account and security against live balances, reporting any nonzero difference in cents or shares, and
- classifies breaks per trade by lining up journal entries against what DvP should have posted: no entries means `missed_settle`, two cash entries means `duplicate_posting`, one entry with the wrong cents means `wrong_amount`.

The wrong-amount case is the one I find most interesting: my injector keeps the corrupted entry double-entry balanced, so a naive "do the books balance" check passes while the per-trade recon still catches it and points at the exact trade.

There is a seeded break injector (`settlecore/generator.py`) that corrupts the live ledger, never the trade log, and returns ground-truth labels, so a recon run can be graded for exact detection and classification, not just "found something".

## Numbers from my machine

Apple silicon (arm64), Python 3.9.6, single thread. Full details and reproduce commands in `RESULTS.md`, raw output in `results/`.

- 100,000 seeded trades through capture to settle in 0.456 s, about 219k trades/sec, then a clean reconciliation with 0 differences in 0.123 s.
- Same story at 500,000 trades: about 222k trades/sec, 0 differences, recon in 0.652 s.
- 75 injected breaks (25 of each type) over the 100k universe: 75 detected, all classified correctly, 0 false positives, 0 false negatives.

## Running it

```
python3 -m venv .venv && .venv/bin/pip install -U pip pytest pytest-cov
.venv/bin/pytest                      # 99 tests
.venv/bin/python -m settlecore.bench  # 100k-trade benchmark, writes results/bench.json
```

## Integer money, enforced

Every amount is an `int` of cents and every share count is an `int`. The `check_cents` and `check_quantity` guards reject floats, bools, strings and `None` at every entry point: trade construction, account opening, and every journal leg. `Ledger.assert_no_floats()` walks every balance and every journal leg after a run as a belt-and-braces check, and the tests assert it on runs of thousands of trades.

## Limitations

- Trades, accounts and prices are synthetic. There is no real market data and no real message formats (no FIX, no SWIFT); a trade is just a dataclass.
- Single currency, equities only, no corporate actions, no fees, no accrued interest. Gross settlement amount is simply quantity times price.
- Everything lives in memory. There is no database, no persistence, and no UI, so a process restart loses state.
- The retry loop is a simple multi-pass sweep, not a real settlement optimizer; it will not find netting opportunities that a smarter sequencer could.
- Break classification assumes at most one break type per trade, which matches how the injector works. Overlapping corruptions on a single trade would be detected but reported as whichever class the decision order hits first.
- Throughput numbers are from one machine, single-threaded, and the workload is uniform random; skewed real-world flow would behave differently.
