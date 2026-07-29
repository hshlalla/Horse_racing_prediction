import requests
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser

URL = "https://race.kra.co.kr/raceScore/ScoretableDetailList.do"
res = requests.post(URL, headers={"User-Agent": "Mozilla/5.0"}, data={"meet": "1", "realRcDate": "20260627", "realRcNo": "2"}, timeout=15)
res.encoding = "euc-kr"
parsed = KRALiveParser.parse_race_detail(res.text)
print("Horses:", len(parsed.get("horses", [])))
print("Scratchings:", len(parsed.get("scratchings", [])))
if parsed.get("scratchings"):
    print("Scratching data:", parsed["scratchings"])
