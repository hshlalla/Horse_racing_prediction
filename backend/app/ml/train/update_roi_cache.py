import asyncio
import json
import os
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.db.models.crawl import Race, RacePrediction
from app.ml.predict.service import predict_race

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "roi_cache.json")

async def update_cache():
    print("Starting ROI cache update...")
    
    async with async_session_factory() as session:
        result = await session.execute(
            select(Race)
            .where(Race.payouts.is_not(None))
        )
        races = result.scalars().all()
        
        print(f"Found {len(races)} races with payouts. Fetching predictions...")
        
        monthly_stats = defaultdict(lambda: {
            "WIN": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
            "QUINELLA": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
            "TRIO": {"investment": 0, "return": 0, "hits": 0, "total_races": 0}
        })
        
        overall_stats = {
            "WIN": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
            "QUINELLA": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
            "TRIO": {"investment": 0, "return": 0, "hits": 0, "total_races": 0}
        }

        # We will process in batches to avoid locking up
        for idx, race in enumerate(races):
            if idx % 100 == 0:
                print(f"Processing race {idx}/{len(races)}...")
                
            month_key = race.race_date.strftime("%Y-%m") if race.race_date else "Unknown"
            
            try:
                race_preds = await predict_race(session, race.id)
            except Exception:
                continue
                
            if not race_preds or len(race_preds) < 3:
                continue
                
            res2 = await session.execute(select(Race).options(selectinload(Race.entries)).where(Race.id == race.id))
            r_loaded = res2.scalars().first()
            if not r_loaded:
                continue
                
            horse_to_num = {e.horse_id: e.program_number for e in r_loaded.entries}
            race_preds.sort(key=lambda x: x.win_probability, reverse=True)
            
            top1_num = str(horse_to_num.get(race_preds[0].horse_id))
            top2_nums = {str(horse_to_num.get(p.horse_id)) for p in race_preds[:2]}
            top3_nums = {str(horse_to_num.get(p.horse_id)) for p in race_preds[:3]}
            
            payouts = race.payouts or {}
            
            for strategy in ["WIN", "QUINELLA", "TRIO"]:
                monthly_stats[month_key][strategy]["total_races"] += 1
                overall_stats[strategy]["total_races"] += 1
            
            # WIN
            inv_win = 1000
            ret_win = 0
            hit_win = 0
            for p in payouts.get("win", []):
                if p["numbers"] == top1_num:
                    ret_win += 1000 * p["odds"]
                    hit_win = 1
            monthly_stats[month_key]["WIN"]["investment"] += inv_win
            monthly_stats[month_key]["WIN"]["return"] += ret_win
            monthly_stats[month_key]["WIN"]["hits"] += hit_win
            overall_stats["WIN"]["investment"] += inv_win
            overall_stats["WIN"]["return"] += ret_win
            overall_stats["WIN"]["hits"] += hit_win
            
            # QUINELLA
            inv_q = 1000
            ret_q = 0
            hit_q = 0
            for p in payouts.get("quinella", []):
                if set(p["numbers"].split("-")) == top2_nums:
                    ret_q += 1000 * p["odds"]
                    hit_q = 1
            monthly_stats[month_key]["QUINELLA"]["investment"] += inv_q
            monthly_stats[month_key]["QUINELLA"]["return"] += ret_q
            monthly_stats[month_key]["QUINELLA"]["hits"] += hit_q
            overall_stats["QUINELLA"]["investment"] += inv_q
            overall_stats["QUINELLA"]["return"] += ret_q
            overall_stats["QUINELLA"]["hits"] += hit_q
            
            # TRIO
            inv_t = 1000
            ret_t = 0
            hit_t = 0
            for p in payouts.get("trio", []):
                if set(p["numbers"].split("-")) == top3_nums:
                    ret_t += 1000 * p["odds"]
                    hit_t = 1
            monthly_stats[month_key]["TRIO"]["investment"] += inv_t
            monthly_stats[month_key]["TRIO"]["return"] += ret_t
            monthly_stats[month_key]["TRIO"]["hits"] += hit_t
            overall_stats["TRIO"]["investment"] += inv_t
            overall_stats["TRIO"]["return"] += ret_t
            overall_stats["TRIO"]["hits"] += hit_t

        # Convert to final output format
        final_data = {
            "overall": overall_stats,
            "monthly": []
        }
        
        for month in sorted(monthly_stats.keys()):
            final_data["monthly"].append({
                "month": month,
                "stats": dict(monthly_stats[month])
            })
            
        with open(CACHE_PATH, "w") as f:
            json.dump(final_data, f, indent=2)
            
        print(f"Successfully saved ROI cache to {CACHE_PATH}")

if __name__ == "__main__":
    asyncio.run(update_cache())
