import asyncio
from sqlalchemy import select
from app.db.session import async_session_factory
from app.db.models.crawl import Race, RacePrediction, RaceEntry
from sqlalchemy.orm import selectinload

async def run_backtest():
    # 1. Fetch all races with payouts and predictions
    async with async_session_factory() as session:
        result = await session.execute(
            select(Race)
            .options(selectinload(Race.entries))
            .where(Race.payouts.is_not(None))
        )
        races = result.scalars().all()
        
        # We need predictions too
        # To avoid N+1 queries, let's load all predictions for these races
        # Wait, let's just predict on the fly!
        from app.ml.predict.service import predict_race
        
        preds_by_race = {}
        for r in races:
            race_preds = await predict_race(session, r.id)
            preds_by_race[r.id] = race_preds
            
        print(f"Loaded {len(races)} races with payouts and predicted them.")
        
        # Strategies:
        # 1. WIN (단승): Bet top 1 AI pick. Payout if Top 1 wins.
        # 2. QUINELLA (복승): Bet top 2 AI picks as a quinella.
        # 3. TRIO (삼복승): Bet top 3 AI picks as a trio.
        
        investments = {"WIN": 0, "QUINELLA": 0, "TRIO": 0}
        returns = {"WIN": 0.0, "QUINELLA": 0.0, "TRIO": 0.0}
        
        for race in races:
            race_preds = preds_by_race[race.id]
            if not race_preds:
                continue
                
            # Map horse_id to program_number
            horse_to_num = {e.horse_id: e.program_number for e in race.entries}
            
            # Sort predictions by win probability descending
            race_preds.sort(key=lambda x: x.win_probability, reverse=True)
            
            if len(race_preds) < 3:
                continue
                
            top1_num = str(horse_to_num.get(race_preds[0].horse_id))
            top2_nums = {str(horse_to_num.get(p.horse_id)) for p in race_preds[:2]}
            top3_nums = {str(horse_to_num.get(p.horse_id)) for p in race_preds[:3]}
            
            payouts = race.payouts or {}
            
            if not payouts:
                continue
                
            # 1. WIN Strategy (bet 1000 won on top 1)
            investments["WIN"] += 1000
            for p in payouts.get("win", []):
                if p["numbers"] == top1_num:
                    returns["WIN"] += 1000 * p["odds"]
                    
            # 2. QUINELLA Strategy (bet 1000 won on top 2 combination)
            investments["QUINELLA"] += 1000
            for p in payouts.get("quinella", []):
                win_comb = set(p["numbers"].split("-"))
                if win_comb == top2_nums:
                    returns["QUINELLA"] += 1000 * p["odds"]
                    
            # 3. TRIO Strategy (bet 1000 won on top 3 combination)
            investments["TRIO"] += 1000
            for p in payouts.get("trio", []):
                win_comb = set(p["numbers"].split("-"))
                if win_comb == top3_nums:
                    returns["TRIO"] += 1000 * p["odds"]
                    
        print("\n--- Backtest Results ---")
        for strategy in ["WIN", "QUINELLA", "TRIO"]:
            inv = investments[strategy]
            ret = returns[strategy]
            roi = ((ret - inv) / inv * 100) if inv > 0 else 0
            print(f"Strategy {strategy}:")
            print(f"  Investment: {inv:,.0f} KRW")
            print(f"  Return:     {ret:,.0f} KRW")
            print(f"  ROI:        {roi:+.2f}%")

if __name__ == "__main__":
    asyncio.run(run_backtest())
