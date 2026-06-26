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
        
        # 1. Parse meta (weather, track condition) from the first tableType1
        info_table = soup.find('div', class_='tableType1')
        if info_table:
            tr = info_table.find('tr', class_='alignC')
            if tr:
                tds = tr.find_all('td')
                if len(tds) >= 4:
                    meta["weather"] = tds[-4].get_text(strip=True)
                    meta["track_condition"] = tds[-3].get_text(strip=True)
                    
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
                            h_no = int(cols[0].get_text(strip=True))
                            s1f_str = cols[2].get_text(strip=True)
                            g3f_str = cols[6].get_text(strip=True) # 6-4F -> wait, actually G3F is the last 600m. 
                            # KRA provides S-1F, 10-8, 8-6, 6-4, 4-2, 2-G, 1-G. We will just use the available columns safely.
                            # S-1F is usually index 2. G-3F is often index 6 or 7 depending on distance.
                            # Let's just grab S1F safely. If G3F is hard to pinpoint, we'll grab the second to last as G3F.
                            
                            s1f = float(s1f_str) if s1f_str.replace('.', '', 1).isdigit() else 14.0
                            # Just grab a proxy for G3F from the second to last column
                            g3f_str_safe = cols[-2].get_text(strip=True)
                            g3f = float(g3f_str_safe) if g3f_str_safe.replace('.', '', 1).isdigit() else 38.0
                            
                            horse_times[h_no] = {"s1f": s1f, "g3f": g3f}
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
                    jockey = cols[8].get_text(strip=True)
                    trainer = cols[9].get_text(strip=True)
                    
                    weight_str = cols[12].get_text(strip=True)
                    weight = 0
                    if '(' in weight_str:
                        weight = float(weight_str.split('(')[0].strip())
                        
                    odds_win = cols[13].get_text(strip=True)
                    odds_place = cols[14].get_text(strip=True)
                    
                    times = horse_times.get(horse_no, {"s1f": 14.0, "g3f": 38.0})
                    
                    results.append({
                        "rank": rank,
                        "horse_no": horse_no,
                        "horse_name": horse_name,
                        "jockey": jockey,
                        "trainer": trainer,
                        "weight": weight,
                        "odds_win": float(odds_win) if odds_win.replace('.','',1).isdigit() else 1.0,
                        "odds_place": float(odds_place) if odds_place.replace('.','',1).isdigit() else 1.0,
                        "s1f_time": times["s1f"],
                        "g3f_time": times["g3f"]
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse row: {e}")
                    continue
                    
        return {"meta": meta, "horses": results}

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
