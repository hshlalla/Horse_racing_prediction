import asyncio, httpx

async def main():
    for r in range(1, 10):
        url = f"https://race.kra.co.kr/down/pdf/jeju/chulma/j_run_hr_20260627_{r:02d}.pdf"
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            if len(res.content) > 1000:
                print(f"Race {r} exists! Downloaded {len(res.content)} bytes.")
                with open(f"jeju_{r}.pdf", "wb") as f:
                    f.write(res.content)
                break
            else:
                print(f"Race {r} failed.")

asyncio.run(main())
