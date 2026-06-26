import asyncio
import random
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.session import engine, async_session_factory
from app.db.base import Base
from app.db.models.crawl import (
    Horse, Jockey, Trainer, Pedigree, Race, RaceEntry, RaceResult, InraceTiming, OddsSnapshot
)

TRACKS = ["SEOUL", "BUSAN", "JEJU"]
START_DATE = datetime.date(2021, 1, 1)
END_DATE = datetime.date(2026, 12, 31)

def random_date(start: datetime.date, end: datetime.date) -> datetime.date:
    return start + datetime.timedelta(days=random.randint(0, (end - start).days))

async def generate_synthetic_data(session: AsyncSession):
    print("Generating Horses, Jockeys, Trainers...")
    horses = []
    for i in range(1, 301):
        h = Horse(
            id=i,
            name=f"Synthetic_Horse_{i}",
            sex=random.choice(["M", "F", "G"]),
            age=random.randint(2, 6),
            breed_origin=random.choice(["KOR", "USA", "JPN"]),
            import_year=random.choice([2019, 2020, 2021, 2022, 2023])
        )
        session.add(h)
        horses.append(h)
    
    jockeys = []
    for i in range(1, 51):
        j = Jockey(id=i, name=f"Jockey_{i}", kra_code=f"J{i:04d}")
        session.add(j)
        jockeys.append(j)

    trainers = []
    for i in range(1, 31):
        t = Trainer(id=i, name=f"Trainer_{i}", kra_code=f"T{i:04d}")
        session.add(t)
        trainers.append(t)
        
    await session.commit()
    
    # Assign intrinsic "ability" scores (0.0 to 1.0)
    horse_ability = {h.id: random.uniform(0.1, 0.9) for h in horses}
    jockey_ability = {j.id: random.uniform(0.2, 0.8) for j in jockeys}
    
    # Generate Pedigree
    print("Generating Pedigree...")
    for i, h in enumerate(horses, 1):
        p = Pedigree(
            id=i,
            horse_id=h.id,
            sire_id=random.choice(horses).id if random.random() < 0.5 else None,
            dam_id=random.choice(horses).id if random.random() < 0.5 else None
        )
        session.add(p)
    await session.commit()

    print("Generating Races (2021-2026)...")
    # Generate 1500 races across the dates
    current_date = START_DATE
    race_id_counter = 1
    entry_id_counter = 1
    result_id_counter = 1
    inrace_id_counter = 1
    odds_id_counter = 1
    
    while current_date <= END_DATE:
        if current_date.weekday() in [5, 6]: # Weekend races
            num_races = random.randint(3, 8)
            for r_num in range(1, num_races + 1):
                track = random.choice(TRACKS)
                race = Race(
                    id=race_id_counter,
                    track=track,
                    race_date=current_date,
                    race_number=r_num,
                    race_name=f"{track} Race {r_num}",
                    distance_m=random.choice([1000, 1200, 1400, 1600, 1800]),
                    surface="SAND",
                    track_condition=random.choice(["DRY", "GOOD", "WET", "MUDDY"]),
                    field_size=random.randint(8, 14),
                    post_time=datetime.datetime.combine(current_date, datetime.time(10 + r_num, 0), tzinfo=datetime.timezone.utc)
                )
                session.add(race)
                race_id_counter += 1
                
                # Entries
                field = random.sample(horses, race.field_size)
                entries = []
                scores = []
                
                for prog_num, h in enumerate(field, 1):
                    j = random.choice(jockeys)
                    t = random.choice(trainers)
                    entry = RaceEntry(
                        id=entry_id_counter,
                        race_id=race.id,
                        horse_id=h.id,
                        jockey_id=j.id,
                        trainer_id=t.id,
                        program_number=prog_num,
                        carry_weight_kg=random.uniform(50, 58),
                        body_weight_kg=random.uniform(450, 550),
                        morning_odds=random.uniform(1.5, 50.0)
                    )
                    session.add(entry)
                    entries.append(entry)
                    entry_id_counter += 1
                    
                    # Score determines finish probability
                    score = horse_ability[h.id] * 0.6 + jockey_ability[j.id] * 0.4 + random.uniform(-0.2, 0.2)
                    scores.append((h.id, score))
                
                # Results (sort by score descending)
                scores.sort(key=lambda x: x[1], reverse=True)
                for pos, (h_id, score) in enumerate(scores, 1):
                    result = RaceResult(
                        id=result_id_counter,
                        race_id=race.id,
                        horse_id=h_id,
                        finish_position=pos,
                        finish_time_s=race.distance_m / 15.0 + (pos * 0.5) + random.uniform(0, 0.5), # Approx 15m/s
                        final_odds=random.uniform(1.1, 80.0)
                    )
                    session.add(result)
                    result_id_counter += 1
                    
                    inrace = InraceTiming(
                        id=inrace_id_counter,
                        race_id=race.id,
                        horse_id=h_id,
                        s1f_time=13.0 + random.uniform(0, 1.5),
                        g3f_time=38.0 + random.uniform(0, 3.0),
                        corner1_rank=random.randint(1, race.field_size)
                    )
                    session.add(inrace)
                    inrace_id_counter += 1
                    
                    odds = OddsSnapshot(
                        id=odds_id_counter,
                        race_id=race.id,
                        horse_id=h_id,
                        snapshot_time=race.post_time - datetime.timedelta(minutes=10),
                        win_odds=result.final_odds,
                        place_odds=result.final_odds / 3.0
                    )
                    session.add(odds)
                    odds_id_counter += 1

        current_date += datetime.timedelta(days=1)

    await session.commit()
    print("Synthetic data generation complete!")

async def main():
    async with engine.begin() as conn:
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session_factory() as session:
        # Check if already populated
        res = await session.execute(select(Horse).limit(1))
        if res.scalars().first() is None:
            await generate_synthetic_data(session)
        else:
            print("Data already exists. Skipping generation.")

if __name__ == "__main__":
    asyncio.run(main())
