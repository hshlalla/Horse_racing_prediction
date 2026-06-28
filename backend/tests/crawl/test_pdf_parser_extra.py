"""Unit tests for _extract_start_training and _extract_swim."""
from app.ml.crawl.crawl_pdf_entries import _extract_start_training, _extract_swim


def test_start_training_pass():
    lines = ["출발훈련:210106(승,양호)", "수영 : 0회 0바퀴"]
    result = _extract_start_training(lines)
    assert result is not None
    assert result["date"] == "210106"
    assert result["passed"] is True


def test_start_training_fail():
    lines = ["출발훈련:210305(불합격,불량)"]
    result = _extract_start_training(lines)
    assert result is not None
    assert result["passed"] is False


def test_start_training_pass_variant():
    lines = ["출발훈련:220915(합격,양호)"]
    result = _extract_start_training(lines)
    assert result is not None
    assert result["passed"] is True


def test_start_training_none():
    result = _extract_start_training(["아무텍스트", "건강기록없음"])
    assert result is None


def test_swim_count():
    lines = ["수영 : 3회 12바퀴"]
    assert _extract_swim(lines) == 3


def test_swim_zero():
    lines = ["수영 : 0회 0바퀴"]
    assert _extract_swim(lines) == 0


def test_swim_none():
    assert _extract_swim(["텍스트없음"]) == 0


def test_swim_no_space():
    lines = ["수영:5회 20바퀴"]
    assert _extract_swim(lines) == 5
