import logging
import time
from typing import List, Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class KRALiveParser:
    """
    Parses live KRA HTML pages for race cards and detailed race results.
    """
    
    @staticmethod
    def parse_time_str(time_str: str) -> float:
        """Parses a time string like '1:20.3' or '0:14.0' into float seconds."""
        if not time_str or not ':' in time_str:
            return 0.0
        try:
            parts = time_str.split(':')
            m = int(parts[0])
            s = float(parts[1])
            return m * 60 + s
        except:
            return 0.0
    
    @staticmethod
    def parse_chulma_list(html_content: str) -> List[Dict[str, Any]]:
        """
        Parses ChulmaDetailInfoList.do to extract upcoming race schedules.
        """
        soup = BeautifulSoup(html_content, 'lxml')
        results = []
        table = soup.find('div', class_='tableType2')
        if not table:
            return results
            
        tbody = table.find('tbody')
        if not tbody:
            return results
            
        for row in tbody.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 4:
                track = cols[1].get_text(strip=True)
                date_link = cols[2].find('a')
                if not date_link:
                    continue
                
                # onclick="ScoreDailyPopup('1','20260621');"
                date_str = ""
                onclick = date_link.get('onclick', '')
                if 'ScoreDailyPopup' in onclick:
                    parts = onclick.split("'")
                    if len(parts) >= 4:
                        date_str = parts[3]
                
                if not date_str:
                    text_date = date_link.get_text(strip=True)
                    date_str = text_date.replace('/', '')
                
                races = []
                for r_link in cols[3].find_all('a'):
                    href = r_link.get('href', '')
                    if 'ScoreDetailPopup' in href:
                        parts = href.split("'")
                        if len(parts) >= 6:
                            try:
                                races.append(int(parts[5]))
                            except ValueError:
                                pass
                                
                if date_str and races:
                    results.append({
                        "date": date_str,
                        "track": track,
                        "races": sorted(list(set(races)))
                    })
        return results

    @staticmethod
    def parse_race_detail(html_content: str) -> Dict[str, Any]:
        """
        Parses ScoretableDetailList.do to extract individual horse performance in a race.
        Returns a dict: {"meta": {...}, "horses": [...]}
        """
        soup = BeautifulSoup(html_content, 'lxml')
        results = []
        meta = {"weather": "맑음", "track_condition": "건조"}
        
        # 1. Parse meta (weather, track condition, distance) from the first tableType1
        info_table = soup.find('div', class_='tableType1')
        if info_table:
            tr = info_table.find('tr', class_='alignC')
            if tr:
                tds = tr.find_all('td')
                if len(tds) >= 4:
                    meta["weather"] = tds[-4].get_text(strip=True)
                    meta["track_condition"] = tds[-3].get_text(strip=True)
                    humidity_txt = tds[-2].get_text(strip=True).replace('%', '')
                    if humidity_txt.isdigit():
                        meta["humidity"] = int(humidity_txt)
                    time_txt = tds[-1].get_text(strip=True)
                    if ':' in time_txt:
                        meta["post_time_str"] = time_txt
            
            for td in info_table.find_all('td'):
                txt = td.get_text(strip=True)
                if txt.endswith('M') and txt[:-1].isdigit():
                    meta["distance_m"] = int(txt[:-1])
                    break
                    
        # 1.5 Parse grade, race_class, surface from race title
        import re

        # KRA race title selector candidates: h4 with race-related class, .raceInfo, .raceName, caption
        title_elem = (
            soup.find("h4", class_=re.compile(r"race", re.I))
            or soup.find(class_=re.compile(r"raceName|raceInfo|raceTitle", re.I))
            or soup.find("caption")
        )
        title_text = title_elem.get_text(strip=True) if title_elem else ""

        # Surface: 잔디 → Turf, anything else (or missing) → Dirt
        if "잔디" in title_text:
            meta["surface"] = "Turf"
        else:
            meta["surface"] = "Dirt"

        # Grade: G1 / G2 / G3 pattern
        grade_match = re.search(r"G[1-3]", title_text)
        meta["grade"] = grade_match.group(0) if grade_match else None

        # Race class: known KRA class keywords
        CLASS_KEYWORDS = ["오픈", "특별", "일반", "선발", "등록", "초청"]
        meta["race_class"] = next(
            (kw for kw in CLASS_KEYWORDS if kw in title_text), None
        )

        # Capture race_name from the title text if available
        if title_text:
            meta["race_name"] = title_text

        # 1.6 Parse YouTube video URL
        youtube_match = re.search(r"youtube\.com/watch\?v=([^'\"]+)", html_content)
        if youtube_match:
            video_id = youtube_match.group(1)
            meta["video_url"] = f"https://www.youtube.com/watch?v={video_id}"
            
        # 2. Parse Sectional Times (S1F, G3F) from the second tableType2 (통과누적기록)
        horse_times = {}
        tables2 = soup.find_all('div', class_='tableType2')
        if len(tables2) >= 2:
            time_table = tables2[1].find('table')
            if time_table:
                for row in time_table.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 9:
                        try:
                            h_no = int(cols[1].get_text(strip=True))
                            horse_no_str = cols[1].get_text(strip=True)
                            if horse_no_str.isdigit():
                                horse_no = int(horse_no_str)
                                s1f_time = KRALiveParser.parse_time_str(cols[3].get_text(strip=True))
                                g3f_time = KRALiveParser.parse_time_str(cols[-3].get_text(strip=True)) if len(cols) >= 3 else 38.0
                                if g3f_time == 0.0: g3f_time = 38.0
                                if s1f_time == 0.0: s1f_time = 14.0
                                
                                # Extract corner ranks using regex
                                import re
                                ranks_list = [int(r) for r in re.findall(r'\d+', cols[2].get_text())]
                                
                                corner1 = corner2 = corner3 = corner4 = corner5 = corner6 = corner7 = None
                                if len(ranks_list) > 0: corner1 = ranks_list[0]
                                if len(ranks_list) > 1: corner2 = ranks_list[1]
                                if len(ranks_list) > 2: corner3 = ranks_list[2]
                                if len(ranks_list) > 3: corner4 = ranks_list[3]
                                if len(ranks_list) > 4: corner5 = ranks_list[4]
                                if len(ranks_list) > 5: corner6 = ranks_list[5]
                                if len(ranks_list) > 6: corner7 = ranks_list[6]
                                    
                                horse_times[horse_no] = {
                                    "s1f": s1f_time, "g3f": g3f_time,
                                    "c1": corner1, "c2": corner2, "c3": corner3, "c4": corner4,
                                    "c5": corner5, "c6": corner6, "c7": corner7
                                }
                        except:
                            pass
        
        # 3. Parse main results
        tables = soup.find_all('table')
        target_table = None
        for t in tables:
            headers = [th.get_text(strip=True) for th in t.find_all('th')]
            if '마명' in headers and '단승' in headers:
                target_table = t
                break
                
        if not target_table:
            meta["completed"] = False
            return {"meta": meta, "horses": results}
            
        rows = target_table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 15:
                try:
                    rank_str = cols[0].get_text(strip=True)
                    if not rank_str.isdigit():
                        continue
                        
                    rank = int(rank_str)
                    horse_no = int(cols[1].get_text(strip=True))
                    horse_name = cols[2].get_text(strip=True)
                    sex = cols[4].get_text(strip=True)
                    
                    age_str = cols[5].get_text(strip=True).replace('세', '')
                    age = int(age_str) if age_str.isdigit() else 3
                    
                    jockey = cols[8].get_text(strip=True)
                    trainer = cols[9].get_text(strip=True)
                    
                    carry_weight_str = cols[6].get_text(strip=True)
                    carry_weight = 0.0
                    if carry_weight_str:
                        # Sometimes it has a * like '*52.5'
                        cw_clean = carry_weight_str.replace('*', '')
                        carry_weight = float(cw_clean) if cw_clean.replace('.', '', 1).isdigit() else 0.0
                        
                    body_weight_str = cols[12].get_text(strip=True)
                    body_weight = 0.0
                    if '(' in body_weight_str:
                        body_weight = float(body_weight_str.split('(')[0].strip())
                        
                    odds_win = cols[13].get_text(strip=True)
                    odds_place = cols[14].get_text(strip=True)
                    
                    times = horse_times.get(horse_no, {
                        "s1f": 14.0, "g3f": 38.0,
                        "c1": None, "c2": None, "c3": None, "c4": None,
                        "c5": None, "c6": None, "c7": None
                    })
                    
                    results.append({
                        "rank": rank,
                        "horse_no": horse_no,
                        "horse_name": horse_name,
                        "sex": sex,
                        "age": age,
                        "jockey": jockey,
                        "trainer": trainer,
                        "carry_weight": carry_weight,
                        "body_weight": body_weight,
                        "odds_win": float(odds_win) if odds_win.replace('.','',1).isdigit() else 1.0,
                        "odds_place": float(odds_place) if odds_place.replace('.','',1).isdigit() else 1.0,
                        "s1f_time": times["s1f"],
                        "g3f_time": times["g3f"],
                        "corner1_rank": times.get("c1"),
                        "corner2_rank": times.get("c2"),
                        "corner3_rank": times.get("c3"),
                        "corner4_rank": times.get("c4"),
                        "corner5_rank": times.get("c5"),
                        "corner6_rank": times.get("c6"),
                        "corner7_rank": times.get("c7")
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse row: {e}")
                    continue
        
        # Mark race as completed when at least one horse has a numeric rank > 0
        meta["completed"] = any(
            isinstance(h.get("rank"), int) and h["rank"] > 0
            for h in results
        )

        # 4. Parse Payouts (배당률)
        payouts = {}
        for td in soup.find_all('td', class_='textLeft'):
            raw = td.get_text()
            if ':' in raw:
                try:
                    bet_type, odds_str = raw.split(':', 1)
                    bet_type = bet_type.strip()
                    
                    import re
                    matches = re.findall(r'([①-⑳]+)\s*([\d\.]+)', odds_str)
                    parsed = []
                    for chars, odds in matches:
                        nums = [str(ord(c) - 9311) for c in chars if 9312 <= ord(c) <= 9331]
                        if nums:
                            parsed.append({"numbers": "-".join(nums), "odds": float(odds)})
                    
                    if parsed:
                        # Normalize key name
                        key_map = {
                            "단승식": "win", "연승식": "place", "복승식": "quinella",
                            "쌍승식": "exacta", "복연승식": "quinella_place",
                            "삼복승식": "trio", "삼쌍승식": "trifecta"
                        }
                        eng_key = key_map.get(bet_type, bet_type)
                        payouts[eng_key] = parsed
                except Exception as e:
                    logger.debug(f"Failed to parse payout {raw}: {e}")

        return {"meta": meta, "horses": results, "payouts": payouts}

    @staticmethod
    def parse_upcoming_race(html_content: str) -> List[Dict[str, Any]]:
        """
        Parses chulmaDetailInfoChulmapyo.do to extract horse entries for an upcoming race.
        """
        soup = BeautifulSoup(html_content, 'lxml')
        results = []
        
        table = soup.find('div', class_='tableType2')
        if not table:
            return results
            
        tbody = table.find('tbody')
        if not tbody:
            return results
            
        for row in tbody.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 10:
                try:
                    horse_no_str = cols[0].get_text(strip=True)
                    if not horse_no_str.isdigit():
                        continue
                        
                    horse_no = int(horse_no_str)
                    horse_name = cols[1].get_text(strip=True)
                    sex = cols[3].get_text(strip=True)
                    age_str = cols[4].get_text(strip=True)
                    age = int(age_str) if age_str.isdigit() else None
                    
                    weight_str = cols[6].get_text(strip=True)
                    weight = float(weight_str) if weight_str else 0.0
                    
                    # Jockey name sometimes has "(-3)Name", clean it
                    jockey = cols[8].get_text(strip=True)
                    if ')' in jockey:
                        jockey = jockey.split(')')[-1].strip()
                        
                    trainer = cols[9].get_text(strip=True)
                    
                    # 취소/제외 마필 필터링 (Filter out canceled or excluded horses)
                    if '취소' in horse_name or '제외' in horse_name or '취소' in jockey:
                        logger.info(f"Skipping canceled horse: {horse_name}")
                        continue
                    
                    
                    results.append({
                        "horse_no": horse_no,
                        "horse_name": horse_name,
                        "sex": sex,
                        "age": age,
                        "weight": weight,
                        "jockey": jockey,
                        "trainer": trainer,
                        # Mock odds since it's an upcoming race without real morning odds on this page
                        "odds_win": 1.0,
                        "odds_place": 1.0
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse upcoming row: {e}")
                    continue
                    
        return results
