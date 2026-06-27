"""
Compare model performance: current (test_dod.db synthetic) vs new (real KRA data from Postgres).

Usage (after crawl has populated Postgres):
    cd backend
    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db uv run python compare_real_vs_synthetic.py
"""
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TRACKS = ["SEOUL", "BUSAN", "JEJU"]
PROD_JSON = Path("models/production.json")
MIN_RACES = 300


def load_production_stats() -> dict:
    if PROD_JSON.exists():
        return json.loads(PROD_JSON.read_text())
    return {}


def check_pg_race_count(db_url: str) -> int:
    import sqlalchemy

    sync_url = (
        db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
              .replace("sqlite+aiosqlite:///", "sqlite:///")
    )
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as conn:
        row = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM races")).fetchone()
    engine.dispose()
    return row[0] if row else 0


def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    # 1. Check data volume
    print("\n=== Checking Postgres race count ===")
    race_count = check_pg_race_count(db_url)
    print(f"  Races in DB: {race_count:,}")
    if race_count < MIN_RACES:
        print(f"  WARNING: only {race_count} races — need at least {MIN_RACES} for reliable training")
        print("  Run more crawling first, or proceed with caution.")
        if race_count == 0:
            sys.exit(1)

    # 2. Record baseline (test_dod.db synthetic models)
    baseline = load_production_stats()
    print("\n=== BASELINE (test_dod.db synthetic data) ===")
    for track in TRACKS:
        info = baseline.get(track, {})
        if info:
            print(f"  {track}: log_loss={info['log_loss']:.4f}  ROI={info['roi']:.4f}  version={info.get('version','?')}")
        else:
            print(f"  {track}: no model")

    # 3. Train on real Postgres data
    print("\n=== TRAINING ON REAL KRA DATA (Postgres) ===")
    from app.ml.train.pipeline import run_train

    results: dict[str, dict] = {}
    for track in TRACKS:
        print(f"\n--- {track} ---")
        try:
            result = run_train(track=track, db_url=db_url)
            results[track] = result
            print(f"  log_loss={result['val_log_loss']:.4f}  ROI={result['val_roi']:.4f}  promoted={result['promoted']}")
        except Exception as exc:
            logger.error("Training failed for %s: %s", track, exc)
            results[track] = {"error": str(exc)}

    # 4. Print comparison table
    print("\n" + "=" * 82)
    print("COMPARISON: synthetic (test_dod.db)  vs  real (Postgres KRA data)")
    print("=" * 82)
    header = f"{'Track':<8}  {'synth log_loss':>14}  {'real log_loss':>13}  {'synth ROI':>10}  {'real ROI':>9}  {'promoted':>9}"
    print(header)
    print("-" * 82)
    for track in TRACKS:
        b = baseline.get(track, {})
        n = results.get(track, {})
        b_ll = f"{b['log_loss']:.4f}" if b.get("log_loss") is not None else "N/A"
        n_ll = f"{n['val_log_loss']:.4f}" if n.get("val_log_loss") is not None else "ERROR"
        b_roi = f"{b['roi']:.4f}" if b.get("roi") is not None else "N/A"
        n_roi = f"{n['val_roi']:.4f}" if n.get("val_roi") is not None else "ERROR"
        promoted = "YES" if n.get("promoted") else ("no" if not n.get("error") else "ERROR")
        # Indicate improvement direction
        try:
            arrow = " <" if float(n_ll) < float(b_ll) else " >"
        except (ValueError, TypeError):
            arrow = ""
        print(f"{track:<8}  {b_ll:>14}  {n_ll + arrow:>13}  {b_roi:>10}  {n_roi:>9}  {promoted:>9}")
    print("=" * 82)
    print("  < = improved (lower log_loss is better)")
    print()


if __name__ == "__main__":
    main()
