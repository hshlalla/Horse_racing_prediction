import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost:5432/db")
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='races'"))
        columns = [row[0] for row in res]
        print(f"Races columns: {columns}")
        
    await engine.dispose()

asyncio.run(main())
