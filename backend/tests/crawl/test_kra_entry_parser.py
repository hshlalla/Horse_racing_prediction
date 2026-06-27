from app.ml.crawl.parsers.kra_live_parser import KRALiveParser

# HTML mimicking ChulmaDetailInfoPrint.do response structure
# div.tableType2 > tbody structure; columns: 마번, 마명, 색모, 성별, 마령, 부담중량, 마체중, 기수코드, 기수, 조교사
SAMPLE_UPCOMING_HTML = """
<html><body>
<div class="tableType2">
<table>
  <thead>
    <tr>
      <th>마번</th><th>마명</th><th>색모</th><th>성별</th><th>마령</th>
      <th>부담중량</th><th>마체중</th><th>기수코드</th><th>기수</th><th>조교사</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td><td>천하무적</td><td>갈</td><td>수</td><td>4</td>
      <td>57.0</td><td>490</td><td>K001</td><td>김철수</td><td>이영희</td>
    </tr>
    <tr>
      <td>2</td><td>날개없는천사</td><td>흑</td><td>암</td><td>3</td>
      <td>54.0</td><td>480(-2)</td><td>K002</td><td>이순신</td><td>강감찬</td>
    </tr>
    <tr>
      <td>취소</td><td>취소말</td><td></td><td>수</td><td>4</td>
      <td>57.0</td><td>500</td><td></td><td>취소기수</td><td>취소조교사</td>
    </tr>
  </tbody>
</table>
</div>
</body></html>
"""

SAMPLE_UPCOMING_WITH_ODDS_HTML = """
<html><body>
<div class="tableType2">
<table>
  <thead>
    <tr>
      <th>마번</th><th>마명</th><th>색모</th><th>성별</th><th>마령</th>
      <th>부담중량</th><th>마체중</th><th>기수코드</th><th>기수</th><th>조교사</th><th>단승</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td><td>천하무적</td><td>갈</td><td>수</td><td>4</td>
      <td>57.0</td><td>490</td><td>K001</td><td>김철수</td><td>이영희</td><td>3.5</td>
    </tr>
  </tbody>
</table>
</div>
</body></html>
"""

EMPTY_HTML = "<html><body><p>데이터 없음</p></body></html>"


def test_parse_upcoming_returns_two_non_cancelled_horses():
    """Non-digit 마번 (취소) rows are skipped."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert len(entries) == 2


def test_parse_upcoming_horse_no():
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert entries[0]["horse_no"] == 1
    assert entries[1]["horse_no"] == 2


def test_parse_upcoming_horse_name():
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert entries[0]["horse_name"] == "천하무적"


def test_parse_upcoming_carry_weight():
    """carry_weight field is present and parsed from 부담중량 column (col[5])."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert "carry_weight" in entries[0]
    assert abs(entries[0]["carry_weight"] - 57.0) < 0.01


def test_parse_upcoming_body_weight_strips_delta():
    """'480(-2)' in col[6] should yield weight=480.0 (delta stripped)."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert abs(entries[1]["weight"] - 480.0) < 0.01


def test_parse_upcoming_jockey_and_trainer():
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert entries[0]["jockey"] == "김철수"
    assert entries[0]["trainer"] == "이영희"


def test_parse_upcoming_morning_odds_none_when_column_absent():
    """When page has no 단승 column, morning_odds is None (not 1.0)."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert "morning_odds" in entries[0]
    assert entries[0]["morning_odds"] is None


def test_parse_upcoming_morning_odds_parsed_when_column_present():
    """When 단승 column exists, morning_odds is parsed as float."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_WITH_ODDS_HTML)
    assert abs(entries[0]["morning_odds"] - 3.5) < 0.01


def test_parse_upcoming_empty_page_returns_empty_list():
    entries = KRALiveParser.parse_upcoming_race(EMPTY_HTML)
    assert entries == []
