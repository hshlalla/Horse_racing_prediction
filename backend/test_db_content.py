import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost:5432/db")
    async with engine.connect() as conn:
        res1 = await conn.execute(text("SELECT count(video_url) FROM races WHERE video_url IS NOT NULL"))
        print(f"Races with video_url: {res1.scalar()}")
        
        res2 = await conn.execute(text("SELECT count(*) FROM race_results"))
        print(f"Race results count: {res2.scalar()}")
        
        res3 = await conn.execute(text("SELECT count(*) FROM horses"))
        print(f"Horses count: {res3.scalar()}")
        
    await engine.dispose()

asyncio.run(main())
