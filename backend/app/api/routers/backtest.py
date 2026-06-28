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
async def get_daily_backtest(date: str = Query(..., description="YYYY-MM-DD format")):
    """Return per-race simulated betting results for a given date."""

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
        # 배당 데이터 있는 경주만 ROI 집계
        totals = {
            "win":      {"investment": 0, "return": 0, "hits": 0, "races_with_payout": 0},
            "quinella": {"investment": 0, "return": 0, "hits": 0, "races_with_payout": 0},
            "trio":     {"investment": 0, "return": 0, "hits": 0, "races_with_payout": 0},
        }

        for race in races:
            payouts = race.payouts or {}
            has_payout = bool(payouts)

            # 결과 로드
            res_q = await session.execute(
                select(RaceResult).where(RaceResult.race_id == race.id)
            )
            results = {r.horse_id: r.finish_position for r in res_q.scalars().all()}

            # 예측 — 실패해도 경주는 포함 (ai_picks=[] 로)
            preds = []
            try:
                preds = await predict_race(session, race.id) or []
            except Exception:
                pass

            preds.sort(key=lambda x: x.win_probability, reverse=True)

            horse_to_num = {e.horse_id: e.program_number for e in race.entries}

            top_picks = preds[:3]

            top1_num = str(horse_to_num.get(top_picks[0].horse_id, "?")) if len(top_picks) >= 1 else None
            top2_nums = {str(horse_to_num.get(p.horse_id, "?")) for p in top_picks[:2]} if len(top_picks) >= 2 else set()
            top3_nums = {str(horse_to_num.get(p.horse_id, "?")) for p in top_picks[:3]} if len(top_picks) >= 3 else set()

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

            # 적중 여부 — 실제 결과 기준
            win_hit = bool(top1_num and actual_top3_nums and actual_top3_nums[0] == top1_num)
            q_hit = bool(top2_nums and len(actual_top3_nums) >= 2 and set(actual_top3_nums[:2]) == top2_nums)
            t_hit = bool(top3_nums and len(actual_top3_nums) >= 3 and set(actual_top3_nums[:3]) == top3_nums)

            # 배당 회수금 (배당 데이터 있을 때만)
            win_return = 0.0
            q_return = 0.0
            t_return = 0.0

            if has_payout and top1_num:
                for p in payouts.get("win", []):
                    if p["numbers"] == top1_num:
                        win_return = 1000 * p["odds"]
                        break
                for p in payouts.get("quinella", []):
                    if set(p["numbers"].split("-")) == top2_nums:
                        q_return = 1000 * p["odds"]
                        break
                for p in payouts.get("trio", []):
                    if set(p["numbers"].split("-")) == top3_nums:
                        t_return = 1000 * p["odds"]
                        break

            # 배당 있는 경주만 ROI 집계
            if has_payout:
                totals["win"]["investment"]          += 1000
                totals["win"]["return"]              += win_return
                totals["win"]["hits"]                += int(win_hit)
                totals["win"]["races_with_payout"]   += 1
                totals["quinella"]["investment"]     += 1000
                totals["quinella"]["return"]         += q_return
                totals["quinella"]["hits"]           += int(q_hit)
                totals["quinella"]["races_with_payout"] += 1
                totals["trio"]["investment"]         += 1000
                totals["trio"]["return"]             += t_return
                totals["trio"]["hits"]               += int(t_hit)
                totals["trio"]["races_with_payout"]  += 1

            race_reports.append({
                "race_id": race.id,
                "track": race.track,
                "race_number": race.race_number,
                "post_time": race.post_time.isoformat() if race.post_time else None,
                "has_payout": has_payout,
                "ai_picks": [
                    {
                        "rank": i + 1,
                        "program_number": horse_to_num.get(p.horse_id),
                        "horse_id": p.horse_id,
                        "win_prob": round(p.win_probability, 4),
                    }
                    for i, p in enumerate(top_picks)
                ],
                "actual_results": actual_top3,
                "bets": {
                    "win":      {"hit": win_hit, "return": win_return},
                    "quinella": {"hit": q_hit,   "return": q_return},
                    "trio":     {"hit": t_hit,   "return": t_return},
                },
            })

    return {
        "date": date,
        "total_races": len(race_reports),
        "races_with_payout": totals["win"]["races_with_payout"],
        "races": race_reports,
        "totals": totals,
    }
