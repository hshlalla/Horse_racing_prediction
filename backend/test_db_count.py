import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost:5432/db")
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT count(*) FROM races"))
        print(f"Races in Postgres: {res.scalar()}")
        
    await engine.dispose()

asyncio.run(main())
