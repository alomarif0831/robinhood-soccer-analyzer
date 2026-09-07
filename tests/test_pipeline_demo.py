from datetime import date

from rsa.config import leagues_from_keys
from rsa.pipeline import analyze, collect, load_bundle, save_bundle, write_outputs
from rsa.synth import DemoKalshiClient, demo_fetch, generate
from rsa.fees import RobinhoodFees


def test_demo_pipeline_end_to_end(tmp_path):
    root = tmp_path / "raw"
    generate(root, seed=3, leagues=["epl", "mls"])
    fetch = demo_fetch(root)
    leagues = leagues_from_keys(["epl", "mls"])
    bundle = collect(leagues, date(2026, 7, 20), date(2026, 9, 6), DemoKalshiClient(root), espn_fetch=fetch, fd_fetch=fetch)
    assert bundle.matches and bundle.warmup and bundle.snapshots
    assert all(m.completed for m in bundle.matches)
    epl = [m for m in bundle.matches if m.league == "epl"]
    assert all("psc_home" in m.odds for m in epl)  # football-data odds merged onto ESPN fixtures
    save_bundle(bundle, tmp_path / "data")
    reloaded = load_bundle(tmp_path / "data")
    assert len(reloaded.matches) == len(bundle.matches) and len(reloaded.snapshots) == len(bundle.snapshots)
    assert reloaded.matches[0].odds.keys() == bundle.matches[0].odds.keys()

    result, df, unmatched = analyze(reloaded, RobinhoodFees(), min_edge=0.02)
    assert result is not None and not unmatched
    assert df["match_id"].nunique() == len(bundle.matches)  # every priced event joined, orientation inferred
    assert df[["book_home", "elo_home", "poisson_home"]].notna().all().all()
    # planted bias: draws priced ~2.5pt below fair
    mv = result.market_vs_book.set_index("outcome")
    assert mv.loc["draw", "mean_diff"] < 0
    path = write_outputs(result, df, unmatched, reloaded, tmp_path / "out", {"synthetic": True, "start": "2026-07-20", "end": "2026-09-06"})
    text = path.read_text(encoding="utf-8")
    assert "SYNTHETIC DEMO DATA" in text and "## Verdict" in text
    assert (tmp_path / "out" / "summary.json").exists() and (tmp_path / "out" / "joined.csv").exists()
