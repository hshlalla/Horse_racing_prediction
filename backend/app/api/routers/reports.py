import datetime
import json
import os
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.db.models.crawl import Race, RaceEntry
from app.ml.predict.service import predict_race

router = APIRouter()

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "roi_cache.json")

@router.get("/roi")
async def get_roi_report():
    if not os.path.exists(CACHE_PATH):
        # Return empty data if not yet generated
        return {
            "overall": {
                "WIN": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
                "QUINELLA": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
                "TRIO": {"investment": 0, "return": 0, "hits": 0, "total_races": 0}
            },
            "monthly": []
        }
    
    try:
        with open(CACHE_PATH, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today-bets")
async def get_today_bets(
    date: str = Query(None, description="YYYY-MM-DD (기본값: 오늘)"),
    min_edge: float = Query(0.0, description="최소 에지 필터 (0.0=전체, 0.05=5%+ 에지만)"),
):
    """오늘 경주별 EV 순위 베팅 추천 — 배당/에지/AI확률 포함."""
    if date is None:
        date = datetime.date.today().isoformat()
    target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Race)
            .options(selectinload(Race.entries))
            .where(Race.race_date == target_date)
            .order_by(Race.post_time)
        )
        races = list(result.scalars().all())

        bet_suggestions = []
        for race in races:
            preds = []
            try:
                preds = await predict_race(session, race.id) or []
            except Exception:
                pass

            if not preds:
                continue

            horse_to_num = {e.horse_id: e.program_number for e in race.entries}
            horse_to_odds = {e.horse_id: (e.morning_odds or 0.0) for e in race.entries}

            # 에지 순서 정렬
            sorted_by_edge = sorted(preds, key=lambda x: x.edge_score, reverse=True)

            picks = []
            for p in sorted_by_edge:
                odds = horse_to_odds.get(p.horse_id, 0.0)
                ev = p.win_probability * odds  # expected value (배당기준)
                picks.append({
                    "program_number": horse_to_num.get(p.horse_id),
                    "horse_id": p.horse_id,
                    "horse_name": p.horse_name,
                    "win_prob": round(p.win_probability, 4),
                    "place_prob": round(p.place_probability, 4),
                    "market_prob": round(p.market_prob, 4),
                    "edge_score": round(p.edge_score, 4),
                    "upset_probability": round(p.upset_probability, 4),
                    "morning_odds": round(odds, 1),
                    "expected_value": round(ev, 3),
                    "top_reasons": p.top_reasons,
                })

            # 에지 필터 적용
            top_pick = picks[0] if picks else None
            ev_qualified = top_pick and top_pick["edge_score"] >= min_edge

            bet_suggestions.append({
                "race_id": race.id,
                "track": race.track,
                "race_number": race.race_number,
                "post_time": race.post_time.isoformat() if race.post_time else None,
                "distance_m": race.distance_m,
                "ev_qualified": ev_qualified,
                "picks": picks[:5],  # 상위 5마리
            })

    qualified = [r for r in bet_suggestions if r["ev_qualified"]]
    return {
        "date": date,
        "min_edge": min_edge,
        "total_races": len(bet_suggestions),
        "qualified_races": len(qualified),
        "races": bet_suggestions,
    }
