from app.ml.crawl.parsers.kra_live_parser import KRALiveParser

SAMPLE_RACE_HTML_TURF = """
<html><body>
<h4 class="raceInfo">제1경주 G3 잔디 1200M</h4>
<div class="tableType1">
  <table><tr class="alignC">
    <td>맑음</td><td>양호</td><td>건조</td><td>65%</td><td>10:00</td>
  </tr></table>
</div>
<div class="tableType2"><table><tbody></tbody></table></div>
</body></html>
"""

SAMPLE_RACE_HTML_DIRT = """
<html><body>
<h4 class="raceInfo">제5경주 오픈 더트 1400M</h4>
<div class="tableType1">
  <table><tr class="alignC">
    <td>흐림</td><td>보통</td><td>습함</td><td>80%</td><td>12:00</td>
  </tr></table>
</div>
<div class="tableType2"><table><tbody></tbody></table></div>
</body></html>
"""

def test_parse_surface_turf():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_TURF)
    assert result["meta"]["surface"] == "Turf"

def test_parse_surface_dirt():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_DIRT)
    assert result["meta"]["surface"] == "Dirt"

def test_parse_grade_g3():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_TURF)
    assert result["meta"]["grade"] == "G3"

def test_parse_race_class_open():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_DIRT)
    assert result["meta"]["race_class"] == "오픈"

def test_parse_defaults_when_no_header():
    result = KRALiveParser.parse_race_detail("<html><body></body></html>")
    assert result["meta"]["surface"] == "Dirt"   # safe default
    assert result["meta"].get("grade") is None
