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


SAMPLE_COMPLETED_HTML = """
<html><body>
<table>
  <tr>
    <th>착순</th><th>마번</th><th>마명</th><th>성</th><th>성별</th><th>마령</th>
    <th>부담중량</th><th>기수</th><th>기수</th><th>조교사</th><th>소유주</th>
    <th>마주</th><th>마체중</th><th>단승</th><th>연승</th>
  </tr>
  <tr>
    <td>1</td><td>3</td><td>천하무적</td><td>수</td><td>M</td><td>4세</td>
    <td>57.0</td><td>김철수</td><td>김철수</td><td>이영희</td><td>박민수</td>
    <td>박민수</td><td>490(+2)</td><td>3.5</td><td>1.8</td>
  </tr>
</table>
</body></html>
"""

SAMPLE_NOT_COMPLETED_HTML = """
<html><body>
<h4 class="raceInfo">제1경주 G1 잔디 1200M</h4>
</body></html>
"""

def test_completed_flag_true_when_result_present():
    result = KRALiveParser.parse_race_detail(SAMPLE_COMPLETED_HTML)
    assert "completed" in result["meta"]
    assert result["meta"]["completed"] is True

def test_completed_flag_false_when_no_results():
    result = KRALiveParser.parse_race_detail(SAMPLE_NOT_COMPLETED_HTML)
    assert "completed" in result["meta"]
    assert result["meta"]["completed"] is False
