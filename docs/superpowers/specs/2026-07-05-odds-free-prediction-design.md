# Odds-Free Prediction — Public Data Expansion (Phase 1)

Date: 2026-07-05
Status: Approved (user), pending implementation plan

## Problem

KRA no longer publishes per-horse pre-race odds on any crawlable public page
(verified across 출마표/chulmainfo, race.kra.co.kr main, e오늘의경주 app,
data.go.kr OpenAPI). `morning_odds` in our DB is backfilled from post-race
성적표, so it exists only for finished races. Because the model is
odds-dominated (77% importance), upcoming races collapse to near-uniform
predictions.

Measured on SEOUL val (515 races, per-race val_log_loss, uniform=2.354):

| config | val_log_loss | skill vs uniform |
|---|---|---|
| A. with odds (current) | 1.859 | +0.495 |
| B. odds removed | 2.065 | +0.289 |
| C. B + previously-dropped features | 2.144 | worse than B |
| D. B + top-3 favorites proxy | **1.912** | **+0.441 (74% recovery)** |

The public main page (`seoulMain.do` 등) exposes, per today's race, the top-3
market favorites (e.g. `1,4,8 ①④ 17.1`). Rank-only, but recovers 74% of the
odds skill (config D). Additionally the 출전상세정보 tabs expose per-horse
data usable as features, all confirmed working for historical dates
(2022/2024/2025 probed) and today's races:

| endpoint (`/chulmainfo/…do`, POST meet/rcDate/rcNo) | data |
|---|---|
| `chulmaDetailInfoStartingTrain` | 출발조교 이력: 조교일자, 기승자, 비고(양호/진입불량/출발자세불량), 출발장구 |
| `chulmaDetailInfoWeight` | 금일체중, 증감, 최종/평균/최고/최저/3위평균 |
| `chulmaDetailInfoTrainState` | 주별 조교(전주/금주 요일별 기승자+횟수) |
| `chulmaDetailInfoAccessoryState` | 진료내역(일자+병명) + 폐출혈 여부 |
| `chulmaDetailInfoStewardsReport` | 심판리포트 텍스트 (Phase 2) |

## Decisions (user-approved)

1. **A안 — unified proxy**: drop odds-value features entirely; use the same
   top-3 rank features for training (derived from historical odds rank) and
   prediction (crawled race morning). No hybrid.
2. **Two-phase scope**: Phase 1 = top-3 proxy + StartingTrain + Weight +
   TrainState + AccessoryState. Phase 2 (later) = StewardsReport text parsing,
   상대전적/거리전적.
3. **Race-day-morning prediction timing** is acceptable (top-3 and 금일체중
   publish that morning). No prior-evening prediction requirement.
4. **Typed tables** following existing crawl→upsert→dataset patterns (no JSON
   blob store).
5. **Backfill all 3 tracks** so shared FEATURES stay dense (avoid the sparse
   train/val-mismatch trap that hurt start_training/swim before).
6. **Edge strategy survives via rank-prior**: market_prob is replaced by the
   historical win rate of fav-rank 1/2/3/other; edge = model_prob − rank_prior.
   Must be re-validated by backtest and thresholds re-tuned.

## Design

### Crawler (`app/ml/crawl/crawl_detail_tabs.py`)
- Fetch the four Phase-1 tabs per (meet, rcDate, rcNo); parse with
  BeautifulSoup; EUC-KR decode; detect the "정상적인 접근이 아닙니다" error
  page; retries with backoff (KRA host DNS flaps).
- Main-page parser for today's top-3 favorites per race
  (`seoulMain.do`/`busanMain.do`/`jejuMain.do` 오늘의경마 table).
- Referer header `chulmainfo/ChulmaDetailInfoList.do…` required.

### Schema
- New `start_training_records(horse_id, train_date, rider, remark, passed,
  equipment)` — full history; `passed` derived (양호→true, *불량→false).
- New `pre_race_workouts(race_id, horse_id, day_label, rider, count)` — raw
  weekly-tab rows.
- Reuse `health_records` for 진료내역 upsert (densifies 2021-2023 coverage);
  폐출혈 stored as a condition value.
- `race_entries.market_fav_rank` (smallint nullable; 1/2/3 else NULL) — filled
  by race-morning crawl; `race_entries` body-weight column filled from 금일체중
  when missing.
- `models/rank_priors.json` artifact: P(win | fav_rank ∈ {1,2,3,other}) from
  training data (per track).

### Backfill (`scripts/backfill_detail_tabs.py`)
- 3 tracks × 2021–2026 (~12k races × 4 tabs ≈ 50k requests @0.4 s ≈ 8–10 h,
  background). Resumable via progress file. Idempotent upserts.
- Extend `scripts/verify_data_integrity.py` with coverage sections for the new
  tables; require ✓ before retrain (project rule).

### Features (dataset.py FEATURES v3; each group ablation-gated)
- Remove: `morning_odds`, `morning_odds_rank`.
- G1 market: `mkt_fav_rank` (1/2/3 else 99), `mkt_is_fav`. Training derives
  from historical odds rank; prediction uses crawled rank. Known risk:
  final-odds rank (train) vs morning popularity rank (predict) distribution
  shift — accepted because ranks are far more stable than odds values;
  monitored via backtest.
- G2 start training: `days_since_start_train`, `start_train_ok_rate`,
  `start_train_count_90d`.
- G3 weight: 금일체중, 증감, `weight_vs_top3avg` (금일체중 − 3위평균).
- G4 workouts: `workout_count_2w`.
- G5 health densify: existing health features on denser data + `eiph_flag`.
- Gate: a group ships only if SEOUL ensemble val_log_loss improves (same
  method as the health-feature experiment).

### Prediction path (service.py)
- Cold-start anchor: inverse-odds → rank-prior anchor (uniform when no rank).
- `market_prob` := normalized rank-prior; `edge_score` = win_prob − market_prob.
- Value model unchanged (trains on historical odds; upset_probability stays
  informational).
- The "배당 미입력" guard becomes a "당일 신호 미입력" guard (fav-rank crawl
  missing ⇒ ev_qualified=false + UI warning).

### Re-validation
- Retrain 3 tracks; existing promotion gate (log_loss + ROI) unchanged.
- `backtest_ev.py`: add rank-prior edge mode; re-validate the SEOUL quinella
  strategy and re-tune `min_edge`; update investment-tab defaults from the
  results.

### Testing
- Parser unit tests against saved HTML fixtures (one per tab + main page).
- dataset feature tests for the new groups; no regressions in the existing
  suite (39 pre-existing failures are the environment baseline).

## Success criteria
- Upcoming-race predictions differentiate horses on race morning
  (no uniform collapse) with val_log_loss ≤ 1.92 (config-D level) after
  feature-group gating.
- Data integrity ✓ after backfill.
- Edge-gated SEOUL strategy re-validated (or explicitly re-scoped) on
  rank-prior edges before the investment tab advertises it.

## Out of scope (Phase 2)
StewardsReport text parsing; 상대전적/해당거리전적 tabs; any use of the
betting (발매) system.
