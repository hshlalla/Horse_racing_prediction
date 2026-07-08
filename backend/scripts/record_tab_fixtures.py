"""Record real KRA HTML fixtures for parser tests.

    DATABASE_URL not needed. Run:  uv run python scripts/record_tab_fixtures.py
"""
from __future__ import annotations

import asyncio
import pathlib

import httpx

KRA = "https://race.kra.co.kr"
H = {
    "User-Agent": "Mozilla/5.0",
    "Referer": KRA + "/chulmainfo/ChulmaDetailInfoList.do?Act=02&Sub=1&meet=1",
}
OUT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"
TABS = {
    "tab_starting_train.html": "chulmaDetailInfoStartingTrain",
    "tab_weight.html": "chulmaDetailInfoWeight",
    "tab_train_state.html": "chulmaDetailInfoTrainState",
    "tab_accessory.html": "chulmaDetailInfoAccessoryState",
}
REF = {"meet": "1", "rcDate": "20260705", "rcNo": "6", "Act": "02", "Sub": "1"}


async def _fetch(client: httpx.AsyncClient, url: str, method: str = "POST", data=None) -> str:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            if method == "POST":
                r = await client.post(url, headers=H, data=data, timeout=25)
            else:
                r = await client.get(url, headers=H, timeout=25)
            html = r.content.decode("euc-kr", errors="replace")
            if "정상적인 접근" in html or len(html) < 2000:
                raise RuntimeError("error page")
            return html
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError(f"failed after 3 attempts: {url}") from last_exc


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(follow_redirects=True) as c:
        for fname, ep in TABS.items():
            html = await _fetch(c, f"{KRA}/chulmainfo/{ep}.do", data=REF)
            (OUT / fname).write_text(html, encoding="utf-8")
            print("saved", fname, len(html))
            await asyncio.sleep(0.4)
        html = await _fetch(c, f"{KRA}/seoulMain.do", method="GET")
        (OUT / "main_seoul.html").write_text(html, encoding="utf-8")
        print("saved main_seoul.html", len(html))


if __name__ == "__main__":
    asyncio.run(main())
