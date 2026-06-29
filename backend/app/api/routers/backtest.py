import datetime
from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional

from app.db.session import async_session_factory
from app.db.models.crawl import Race, RaceEntry, RaceResult
from app.ml.predict.service import predict_race

router = APIRouter()


@router.get("/backtest")
async def get_daily_backtest(
    date: str = Query(..., description="YYYY-MM-DD format"),
    min_edge: float = Query(0.0, description="최소 에지 필터 (0.0=전체, 0.05=5% 이상만)"),
):
    """Return per-race simulated betting results for a given date for all 7 bet types."""

    target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Race)
            .options(selectinload(Race.entries))
            .where(Race.race_date == target_date)
            .order_by(Race.post_time)
        )
        races = list(result.scalars().all())

        race_reports = []
        # 배당 데이터 있는 경주만 ROI 집계 (7종 승식)
        bet_types = ["win", "place", "quinella", "exacta", "quinella_place", "trio", "trifecta"]
        totals = {bt: {"investment": 0, "return": 0, "hits": 0, "races_with_payout": 0} for bt in bet_types}

        for race in races:
            payouts = race.payouts or {}
            has_payout = bool(payouts)

            # 결과 로드
            res_q = await session.execute(
                select(RaceResult).where(RaceResult.race_id == race.id)
            )
            results = {r.horse_id: r.finish_position for r in res_q.scalars().all()}

            # 예측 — 실패해도 경주는 포함
            preds = []
            try:
                preds = await predict_race(session, race.id) or []
            except Exception:
                pass

            win_sorted = sorted(preds, key=lambda x: x.win_probability, reverse=True)
            place_sorted = sorted(preds, key=lambda x: x.place_probability, reverse=True)

            w1, w2, w3 = (win_sorted[0] if len(win_sorted) > 0 else None,
                          win_sorted[1] if len(win_sorted) > 1 else None,
                          win_sorted[2] if len(win_sorted) > 2 else None)
            
            p1, p2 = (place_sorted[0] if len(place_sorted) > 0 else None,
                      place_sorted[1] if len(place_sorted) > 1 else None)

            horse_to_num = {e.horse_id: e.program_number for e in race.entries}
            
            num = lambda p: str(horse_to_num.get(p.horse_id, "?")) if p else None
            w1_n, w2_n, w3_n = num(w1), num(w2), num(w3)
            p1_n, p2_n = num(p1), num(p2)

            # 실제 1·2·3착
            sorted_results = sorted(results.items(), key=lambda x: x[1] if x[1] else 999)
            actual_top3 = []
            for hid, pos in sorted_results[:3]:
                actual_top3.append({
                    "horse_id": hid,
                    "program_number": horse_to_num.get(hid),
                    "finish_position": pos,
                })
            actual_top3_nums = [str(a["program_number"]) for a in actual_top3 if a["program_number"]]

            a_top1 = actual_top3_nums[0] if len(actual_top3_nums) >= 1 else None
            a_top2 = actual_top3_nums[:2]
            a_top3 = actual_top3_nums[:3]

            # 적중 여부 — 실제 결과 기준
            win_hit = bool(w1_n and a_top1 == w1_n)
            place_hit = bool(p1_n and p1_n in a_top3)
            q_hit = bool(w1_n and w2_n and len(a_top2) >= 2 and set(a_top2) == {w1_n, w2_n})
            e_hit = bool(w1_n and w2_n and len(a_top2) >= 2 and a_top2 == [w1_n, w2_n])
            qp_hit = bool(p1_n and p2_n and len(a_top3) >= 2 and {p1_n, p2_n}.issubset(set(a_top3)))
            t_hit = bool(w1_n and w2_n and w3_n and len(a_top3) >= 3 and set(a_top3) == {w1_n, w2_n, w3_n})
            tf_hit = bool(w1_n and w2_n and w3_n and len(a_top3) >= 3 and a_top3 == [w1_n, w2_n, w3_n])

            # 배당 회수금
            win_return = 0.0
            place_return = 0.0
            q_return = 0.0
            e_return = 0.0
            qp_return = 0.0
            t_return = 0.0
            tf_return = 0.0

            if has_payout:
                for p in payouts.get("win", []):
                    if p["numbers"] == w1_n:
                        win_return = 1000 * p["odds"]
                        break
                for p in payouts.get("place", []):
                    if p["numbers"] == p1_n:
                        place_return = 1000 * p["odds"]
                        break
                for p in payouts.get("quinella", []):
                    if set(p["numbers"].split("-")) == {w1_n, w2_n}:
                        q_return = 1000 * p["odds"]
                        break
                for p in payouts.get("exacta", []):
                    if p["numbers"] == f"{w1_n}-{w2_n}":
                        e_return = 1000 * p["odds"]
                        break
                for p in payouts.get("quinella_place", []):
                    if set(p["numbers"].split("-")) == {p1_n, p2_n}:
                        qp_return = 1000 * p["odds"]
                        break
                for p in payouts.get("trio", []):
                    if set(p["numbers"].split("-")) == {w1_n, w2_n, w3_n}:
                        t_return = 1000 * p["odds"]
                        break
                for p in payouts.get("trifecta", []):
                    if p["numbers"] == f"{w1_n}-{w2_n}-{w3_n}":
                        tf_return = 1000 * p["odds"]
                        break

            # EV 필터: min_edge 이상인 말이 top pick일 때만 베팅
            top_edge = w1.edge_score if w1 else 0.0
            ev_bet = top_edge >= min_edge if min_edge > 0.0 else True

            # 배당 있는 경주만 ROI 집계 (EV 필터 적용)
            if has_payout and ev_bet:
                def add_stats(bt, hit, ret):
                    totals[bt]["investment"] += 1000
                    totals[bt]["return"] += ret
                    totals[bt]["hits"] += int(hit)
                    totals[bt]["races_with_payout"] += 1

                add_stats("win", win_hit, win_return)
                add_stats("place", place_hit, place_return)
                add_stats("quinella", q_hit, q_return)
                add_stats("exacta", e_hit, e_return)
                add_stats("quinella_place", qp_hit, qp_return)
                add_stats("trio", t_hit, t_return)
                add_stats("trifecta", tf_hit, tf_return)

            race_reports.append({
                "race_id": race.id,
                "track": race.track,
                "race_number": race.race_number,
                "post_time": race.post_time.isoformat() if race.post_time else None,
                "has_payout": has_payout,
                "ev_bet": ev_bet,
                "top_edge": round(top_edge, 4),
                "ai_picks": [
                    {
                        "rank": i + 1,
                        "program_number": horse_to_num.get(p.horse_id),
                        "horse_id": p.horse_id,
                        "horse_name": p.horse_name,
                        "win_prob": round(p.win_probability, 4),
                        "market_prob": round(p.market_prob, 4),
                        "edge_score": round(p.edge_score, 4),
                        "morning_odds": round(
                            next(
                                (e.morning_odds for e in race.entries if e.horse_id == p.horse_id),
                                0.0
                            ) or 0.0,
                            1,
                        ),
                    }
                    for i, p in enumerate(win_sorted[:3])
                ],
                "actual_results": actual_top3,
                "bets": {
                    "win":            {"hit": win_hit and ev_bet, "return": win_return if ev_bet else 0},
                    "place":          {"hit": place_hit and ev_bet, "return": place_return if ev_bet else 0},
                    "quinella":       {"hit": q_hit and ev_bet,   "return": q_return if ev_bet else 0},
                    "exacta":         {"hit": e_hit and ev_bet, "return": e_return if ev_bet else 0},
                    "quinella_place": {"hit": qp_hit and ev_bet, "return": qp_return if ev_bet else 0},
                    "trio":           {"hit": t_hit and ev_bet,   "return": t_return if ev_bet else 0},
                    "trifecta":       {"hit": tf_hit and ev_bet, "return": tf_return if ev_bet else 0},
                },
            })

    return {
        "date": date,
        "total_races": len(race_reports),
        "races_with_payout": totals["win"]["races_with_payout"],
        "races": race_reports,
        "totals": totals,
    }
