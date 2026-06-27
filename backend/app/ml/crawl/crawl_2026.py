import asyncio
import logging
import requests
import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.db.models.crawl import Horse, Jockey, Trainer, Race, RaceEntry, RaceResult, InraceTiming, OddsSnapshot
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

async def get_or_create(session, model, **kwargs):
    stmt = select(model).filter_by(**kwargs)
    result = await session.execute(stmt)
    instance = result.scalars().first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        await session.flush()
        return instance

async def crawl_and_save_date(session, rc_date: str, meet: str = "1"):
    # meet: 1=SEOUL, 2=JEJU, 3=BUSAN
    track_map = {"1": "SEOUL", "2": "JEJU", "3": "BUSAN"}
    track_name = track_map.get(meet, "SEOUL")
    
    logger.info(f"Fetching races for {rc_date} at {track_name}...")
    try:
        res_list = requests.post(
            "https://race.kra.co.kr/raceScore/ScoretableScoreList.do",
            headers={"User-Agent": "Mozilla/5.0"},
            data={"Act": "04", "Sub": "1", "meet": meet, "rcDate": rc_date},
            timeout=10
        )
        res_list.encoding = 'euc-kr'
        live_races = KRALiveParser.parse_chulma_list(res_list.text)
        
        target_date_info = next((r for r in live_races if r['date'] == rc_date), None)
        if not target_date_info or not target_date_info['races']:
            logger.info(f"No races found for {rc_date}.")
            return

        races = target_date_info['races']
        logger.info(f"Found {len(races)} races on {rc_date}. Crawling details...")

        for rc_no in races:
            d_obj = datetime.datetime.strptime(rc_date, "%Y%m%d").date()
            
            # Delete old race to backfill
            stmt = select(Race).filter_by(track=track_name, race_date=d_obj, race_number=rc_no)
            res = await session.execute(stmt)
            old_race = res.scalars().first()
            if old_race:
                # Delete related records
                await session.execute(RaceEntry.__table__.delete().where(RaceEntry.race_id == old_race.id))
                await session.execute(RaceResult.__table__.delete().where(RaceResult.race_id == old_race.id))
                await session.execute(InraceTiming.__table__.delete().where(InraceTiming.race_id == old_race.id))
                await session.delete(old_race)
                await session.flush()

            await asyncio.sleep(1) # delay to prevent blocking
            logger.info(f"Fetching {rc_date} Race {rc_no}...")
            res = requests.post(
                "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
                headers={"User-Agent": "Mozilla/5.0"},
                data={"meet": meet, "realRcDate": rc_date, "realRcNo": str(rc_no)},
                timeout=10
            )
            res.encoding = 'euc-kr'
            parsed_data = KRALiveParser.parse_race_detail(res.text)
            
            if not parsed_data or not parsed_data.get('horses'):
                continue
                
            meta = parsed_data['meta']
            details = parsed_data['horses']

            # Create Race
            pt_str = meta.get("post_time_str")
            post_time_dt = None
            if pt_str:
                try:
                    pt_time = datetime.datetime.strptime(pt_str, "%H:%M").time()
                    post_time_dt = datetime.datetime.combine(d_obj, pt_time)
                except Exception:
                    pass

            race = Race(
                track=track_name,
                race_date=d_obj,
                race_number=rc_no,
                race_name=meta.get("race_name", f"Race {rc_no}"),
                distance_m=meta.get("distance_m", 1200),
                surface=meta.get("surface", "Dirt"),
                grade=meta.get("grade"),
                race_class=meta.get("race_class"),
                field_size=len(details),
                weather=meta.get("weather", "맑음"),
                track_condition=meta.get("track_condition", "건조"),
                video_url=meta.get("video_url"),
                payouts=parsed_data.get("payouts"),
                post_time=post_time_dt
            )
            session.add(race)
            await session.flush()

            for idx, d in enumerate(details):
                horse = await get_or_create(session, Horse, name=d['horse_name'], sex="M")
                d["_horse_db_id"] = horse.id
                jockey = await get_or_create(session, Jockey, name=d['jockey'])
                trainer = await get_or_create(session, Trainer, name=d['trainer'])

                entry = RaceEntry(
                    race_id=race.id,
                    horse_id=horse.id,
                    jockey_id=jockey.id,
                    trainer_id=trainer.id,
                    program_number=d['horse_no'],
                    carry_weight_kg=d.get('carry_weight', 53.0),
                    body_weight_kg=d.get('weight'),
                    morning_odds=d.get('odds_win')
                )
                session.add(entry)

                result = RaceResult(
                    race_id=race.id,
                    horse_id=horse.id,
                    finish_position=d['rank'],
                    final_odds=d.get('odds_win')
                )
                session.add(result)

                timing = InraceTiming(
                    race_id=race.id,
                    horse_id=horse.id,
                    s1f_time=d.get('s1f_time', 14.0),
                    g3f_time=d.get('g3f_time', 38.0)
                )
                session.add(timing)

            # Save odds snapshots for live/upcoming races (not completed ones)
            if not parsed_data.get("meta", {}).get("completed", False):
                snapshot_time = datetime.datetime.now(datetime.timezone.utc)
                for horse_data in details:
                    horse_id_snap = horse_data.get("_horse_db_id")
                    if not horse_id_snap or not race:
                        continue
                    odds_win = horse_data.get("odds_win")
                    if odds_win is None:
                        continue
                    snap = OddsSnapshot(
                        race_id=race.id,
                        horse_id=horse_id_snap,
                        snapshot_time=snapshot_time,
                        win_odds=float(odds_win),
                        place_odds=horse_data.get("odds_place"),
                    )
                    session.add(snap)

            await session.commit()
            logger.info(f"Saved {len(details)} results for Race {rc_no} with weather {meta.get('weather')}.")

    except Exception as e:
        logger.error(f"Failed to crawl {rc_date}: {e}")
        await session.rollback()

async def crawl_date_bruteforce(session, rc_date: str, meet: str = "1"):
    # meet: 1=SEOUL, 2=JEJU, 3=BUSAN
    track_map = {"1": "SEOUL", "2": "JEJU", "3": "BUSAN"}
    track_name = track_map.get(meet, "SEOUL")
    
    logger.info(f"Brute-forcing races for {rc_date} at {track_name}...")
    try:
        found_any = False
        for rc_no in range(1, 16): # typically max 15 races
            await asyncio.sleep(0.5) # delay to prevent blocking
            res = requests.post(
                "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
                headers={"User-Agent": "Mozilla/5.0"},
                data={"meet": meet, "realRcDate": rc_date, "realRcNo": str(rc_no)},
                timeout=10
            )
            res.encoding = 'euc-kr'
            parsed_data = KRALiveParser.parse_race_detail(res.text)
            
            if not parsed_data or not parsed_data.get('horses'):
                if rc_no > 5 and not found_any:
                    # If we checked up to race 5 and found nothing, assume no races today
                    break
                continue
                
            found_any = True
            meta = parsed_data['meta']
            details = parsed_data['horses']

            d_obj = datetime.datetime.strptime(rc_date, "%Y%m%d").date()
            
            # Delete old race to backfill
            stmt = select(Race).filter_by(track=track_name, race_date=d_obj, race_number=rc_no)
            res_db = await session.execute(stmt)
            old_race = res_db.scalars().first()
            if old_race:
                await session.execute(RaceEntry.__table__.delete().where(RaceEntry.race_id == old_race.id))
                await session.execute(RaceResult.__table__.delete().where(RaceResult.race_id == old_race.id))
                await session.execute(InraceTiming.__table__.delete().where(InraceTiming.race_id == old_race.id))
                await session.delete(old_race)
                await session.flush()

            pt_str = meta.get("post_time_str")
            post_time_dt = None
            if pt_str:
                try:
                    pt_time = datetime.datetime.strptime(pt_str, "%H:%M").time()
                    post_time_dt = datetime.datetime.combine(d_obj, pt_time)
                except Exception:
                    pass

            # Create Race
            race = Race(
                track=track_name,
                race_date=d_obj,
                race_number=rc_no,
                race_name=meta.get("race_name", f"Race {rc_no}"),
                distance_m=meta.get("distance_m", 1200),
                surface=meta.get("surface", "Dirt"),
                grade=meta.get("grade"),
                race_class=meta.get("race_class"),
                field_size=len(details),
                weather=meta.get("weather", "맑음"),
                track_condition=meta.get("track_condition", "건조"),
                video_url=meta.get("video_url"),
                payouts=parsed_data.get("payouts"),
                post_time=post_time_dt
            )
            session.add(race)
            await session.flush()

            for idx, d in enumerate(details):
                horse = await get_or_create(session, Horse, name=d['horse_name'], sex="M")
                d["_horse_db_id"] = horse.id
                jockey = await get_or_create(session, Jockey, name=d['jockey'])
                trainer = await get_or_create(session, Trainer, name=d['trainer'])

                entry = RaceEntry(
                    race_id=race.id,
                    horse_id=horse.id,
                    jockey_id=jockey.id,
                    trainer_id=trainer.id,
                    program_number=d['horse_no'],
                    carry_weight_kg=d.get('carry_weight', 53.0),
                    body_weight_kg=d.get('weight'),
                    morning_odds=d.get('odds_win')
                )
                session.add(entry)

                result = RaceResult(
                    race_id=race.id,
                    horse_id=horse.id,
                    finish_position=d['rank'],
                    final_odds=d.get('odds_win')
                )
                session.add(result)

                timing = InraceTiming(
                    race_id=race.id,
                    horse_id=horse.id,
                    s1f_time=d.get('s1f_time', 14.0),
                    g3f_time=d.get('g3f_time', 38.0)
                )
                session.add(timing)

            # Save odds snapshots for live/upcoming races (not completed ones)
            if not parsed_data.get("meta", {}).get("completed", False):
                snapshot_time = datetime.datetime.now(datetime.timezone.utc)
                for horse_data in details:
                    horse_id_snap = horse_data.get("_horse_db_id")
                    if not horse_id_snap or not race:
                        continue
                    odds_win = horse_data.get("odds_win")
                    if odds_win is None:
                        continue
                    snap = OddsSnapshot(
                        race_id=race.id,
                        horse_id=horse_id_snap,
                        snapshot_time=snapshot_time,
                        win_odds=float(odds_win),
                        place_odds=horse_data.get("odds_place"),
                    )
                    session.add(snap)

            await session.commit()
            logger.info(f"Saved {len(details)} results for {rc_date} Race {rc_no} with weather {meta.get('weather')}.")

        if not found_any:
            logger.info(f"No races found for {rc_date} at {track_name} (brute-forced 1-15).")
            
    except Exception as e:
        logger.error(f"Failed to crawl {rc_date}: {e}")
        await session.rollback()

async def crawl_2026():
    # Generate weekend dates for 2026 (up to June)
    dates = []
    start = datetime.date(2026, 1, 1)
    end = datetime.date(2026, 6, 26)
    curr = start
    while curr <= end:
        if curr.weekday() in [5, 6]: # Saturday, Sunday
            dates.append(curr.strftime("%Y%m%d"))
        curr += datetime.timedelta(days=1)
    
    async with async_session_factory() as session:
        for d in dates:
            await crawl_and_save_date(session, d, meet="1") # Seoul
            
    logger.info("2026 Crawl Complete!")

if __name__ == "__main__":
    asyncio.run(crawl_2026())
