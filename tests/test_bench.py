from settlecore.bench import run_bench


def test_bench_small_run_produces_clean_recon_and_exact_breaks():
    results = run_bench(n_trades=2_000, seed=5)
    assert results["settled"] + results["failed"] == 2_000
    assert results["clean_recon"] is True
    assert results["clean_diff_count"] == 0
    assert results["breaks_injected"] == 75
    assert results["breaks_detected"] == 75
    assert results["classification_exact_match"] is True
    assert results["false_positives"] == 0
    assert results["false_negatives"] == 0
    assert results["trades_per_second"] > 0
