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
        totals = {
            "win": {"investment": 0, "return": 0, "hits": 0},
            "quinella": {"investment": 0, "return": 0, "hits": 0},
            "trio": {"investment": 0, "return": 0, "hits": 0},
        }

        for race in races:
            payouts = race.payouts or {}
            if not payouts:
                continue

            # Load results
            res_q = await session.execute(
                select(RaceResult).where(RaceResult.race_id == race.id)
            )
            results = {r.horse_id: r.finish_position for r in res_q.scalars().all()}

            # Load predictions
            try:
                preds = await predict_race(session, race.id)
            except Exception:
                continue

            if not preds or len(preds) < 3:
                continue

            preds.sort(key=lambda x: x.win_probability, reverse=True)

            horse_to_num = {e.horse_id: e.program_number for e in race.entries}
            horse_to_name = {}
            for e in race.entries:
                # Load horse name
                horse_to_name[e.horse_id] = getattr(e, '_horse_name', str(e.program_number))

            top1 = preds[0]
            top2 = preds[1]
            top3 = preds[2]

            top1_num = str(horse_to_num.get(top1.horse_id, "?"))
            top2_nums = {str(horse_to_num.get(p.horse_id, "?")) for p in preds[:2]}
            top3_nums = {str(horse_to_num.get(p.horse_id, "?")) for p in preds[:3]}

            # Actual 1st, 2nd, 3rd
            sorted_results = sorted(results.items(), key=lambda x: x[1] if x[1] else 999)
            actual_top3 = []
            for hid, pos in sorted_results[:3]:
                actual_top3.append({
                    "horse_id": hid,
                    "program_number": horse_to_num.get(hid),
                    "finish_position": pos,
                })

            # Check WIN
            win_hit = False
            win_return = 0
            for p in payouts.get("win", []):
                if p["numbers"] == top1_num:
                    win_return = 1000 * p["odds"]
                    win_hit = True

            # Check QUINELLA
            q_hit = False
            q_return = 0
            for p in payouts.get("quinella", []):
                if set(p["numbers"].split("-")) == top2_nums:
                    q_return = 1000 * p["odds"]
                    q_hit = True

            # Check TRIO
            t_hit = False
            t_return = 0
            for p in payouts.get("trio", []):
                if set(p["numbers"].split("-")) == top3_nums:
                    t_return = 1000 * p["odds"]
                    t_hit = True

            totals["win"]["investment"] += 1000
            totals["win"]["return"] += win_return
            totals["win"]["hits"] += int(win_hit)
            totals["quinella"]["investment"] += 1000
            totals["quinella"]["return"] += q_return
            totals["quinella"]["hits"] += int(q_hit)
            totals["trio"]["investment"] += 1000
            totals["trio"]["return"] += t_return
            totals["trio"]["hits"] += int(t_hit)

            race_reports.append({
                "race_id": race.id,
                "track": race.track,
                "race_number": race.race_number,
                "post_time": race.post_time.isoformat() if race.post_time else None,
                "ai_picks": [
                    {"rank": 1, "program_number": horse_to_num.get(top1.horse_id), "horse_id": top1.horse_id, "win_prob": round(top1.win_probability, 4)},
                    {"rank": 2, "program_number": horse_to_num.get(top2.horse_id), "horse_id": top2.horse_id, "win_prob": round(top2.win_probability, 4)},
                    {"rank": 3, "program_number": horse_to_num.get(top3.horse_id), "horse_id": top3.horse_id, "win_prob": round(top3.win_probability, 4)},
                ],
                "actual_results": actual_top3,
                "bets": {
                    "win": {"hit": win_hit, "return": win_return, "odds": payouts.get("win", [{}])[0].get("odds", 0) if win_hit else 0},
                    "quinella": {"hit": q_hit, "return": q_return},
                    "trio": {"hit": t_hit, "return": t_return},
                }
            })

    return {
        "date": date,
        "total_races": len(race_reports),
        "races": race_reports,
        "totals": totals,
    }
