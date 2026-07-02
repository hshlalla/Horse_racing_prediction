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
    track: str = Query(None, description="트랙 필터 SEOUL/BUSAN/JEJU (기본 전체)"),
):
    """경주별 베팅 추천 — 백테스트 검증 전략(모델 본선마 승률순 + 에지 게이트).

    단승=승률 1위 말, 복승=승률 상위 2마리 조합. ev_qualified는 본선마(승률
    1위)의 에지가 min_edge 이상인지로 판정한다. 배당/에지/AI확률/역배확률 포함.
    """
    if date is None:
        date = datetime.date.today().isoformat()
    target_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    async with async_session_factory() as session:
        query = (
            select(Race)
            .options(selectinload(Race.entries))
            .where(Race.race_date == target_date)
        )
        if track:
            query = query.where(Race.track == track.upper())
        result = await session.execute(query.order_by(Race.post_time))
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

            # 승률순 정렬 — 백테스트에서 검증한 전략은 "모델 본선마(승률 1위)에
            # 에지가 있을 때 그 말/상위2에 베팅". 에지순 정렬은 미검증(역배 성격,
            # -4% 백테스트)이라 승률순으로 정렬한다.
            sorted_by_prob = sorted(preds, key=lambda x: x.win_probability, reverse=True)

            picks = []
            for p in sorted_by_prob:
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

            # 에지 필터: 본선마(승률 1위)의 에지가 min_edge 이상일 때만 추천
            top_pick = picks[0] if picks else None
            ev_qualified = bool(top_pick and top_pick["edge_score"] >= min_edge)

            # 복승(quinella) 추천 = 승률 상위 2마리 조합 (백테스트 최고 수익 전략)
            quinella = None
            if len(picks) >= 2:
                quinella = {
                    "numbers": [picks[0]["program_number"], picks[1]["program_number"]],
                    "horse_names": [picks[0]["horse_name"], picks[1]["horse_name"]],
                    "combined_win_prob": round(picks[0]["win_prob"] + picks[1]["win_prob"], 4),
                }

            bet_suggestions.append({
                "race_id": race.id,
                "track": race.track,
                "race_number": race.race_number,
                "post_time": race.post_time.isoformat() if race.post_time else None,
                "distance_m": race.distance_m,
                "ev_qualified": ev_qualified,
                "quinella": quinella,
                "picks": picks[:5],  # 상위 5마리
            })

    qualified = [r for r in bet_suggestions if r["ev_qualified"]]
    return {
        "date": date,
        "min_edge": min_edge,
        "track": track,
        "total_races": len(bet_suggestions),
        "qualified_races": len(qualified),
        "races": bet_suggestions,
    }
