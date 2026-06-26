import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def parse_race_list_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Parses the KRA Race Score List HTML (e.g., seoulMain.do) to extract dates and races.
    Returns a list of dictionaries:
    [
        {
            "date": "20260621",
            "track": "서울",
            "races": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        },
        ...
    ]
    """
    soup = BeautifulSoup(html_content, 'lxml')
    results = []
    
    # Find the table with class 'tableType2'
    table = soup.find('div', class_='tableType2')
    if not table:
        logger.warning("Could not find div.tableType2 in HTML.")
        return results
        
    tbody = table.find('tbody')
    if not tbody:
        logger.warning("Could not find tbody in tableType2.")
        return results
        
    rows = tbody.find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 4:
            track = cols[1].get_text(strip=True)
            
            # Extract date from the onclick attribute or text
            date_link = cols[2].find('a')
            if not date_link:
                continue
                
            onclick_attr = date_link.get('onclick', '')
            # e.g., ScoreDailyPopup('1','20260621')
            date_str = ""
            if "ScoreDailyPopup" in onclick_attr:
                parts = onclick_attr.split("'")
                if len(parts) >= 4:
                    date_str = parts[3]
            
            if not date_str:
                # Fallback to parsing text "2026/06/21"
                text_date = date_link.contents[0].strip() if date_link.contents else ""
                date_str = text_date.replace('/', '')
                
            # Extract races
            races = []
            race_links = cols[3].find_all('a')
            for r_link in race_links:
                href = r_link.get('href', '')
                if 'ScoreDetailPopup' in href:
                    # e.g., javascript:ScoreDetailPopup('1','20260621','1');
                    parts = href.split("'")
                    if len(parts) >= 6:
                        try:
                            race_num = int(parts[5])
                            races.append(race_num)
                        except ValueError:
                            pass
            
            if date_str and races:
                results.append({
                    "date": date_str,
                    "track": track,
                    "races": sorted(list(set(races)))
                })
                
    return results

if __name__ == "__main__":
    # Test with dummy data
    sample_html = '''
    <div class="tableType2">
        <table>
            <tbody>
                <tr>
                    <td>1</td>
                    <td>서울</td>
                    <td>
                        <a href="#" onclick="ScoreDailyPopup('1','20260621'); return false;">2026/06/21</a>
                    </td>
                    <td>
                        <a href="javascript:ScoreDetailPopup('1','20260621','1');">1</a>
                        <a href="javascript:ScoreDetailPopup('1','20260621','2');">2</a>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    '''
    print(parse_race_list_html(sample_html))
