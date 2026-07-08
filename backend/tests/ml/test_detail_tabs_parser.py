from __future__ import annotations

import datetime
import pathlib

import pytest

from app.ml.crawl.parsers.detail_tabs_parser import (
    parse_starting_train, parse_weight, parse_train_state,
    parse_accessory_medical, parse_main_top3,
)

FIX = pathlib.Path(__file__).resolve().parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_starting_train_rows():
    rows = parse_starting_train(_read("tab_starting_train.html"))
    assert len(rows) >= 5
    r = rows[0]
    assert r["program_number"] == 1 and r["horse_name"] == "파사퀸"
    assert r["train_date"] == datetime.date(2026, 7, 1)
    assert r["remark"] == "양호" and r["passed"] is True
    assert r["equipment"] == "꼬리받침"
    # every row typed
    assert all(isinstance(x["train_date"], datetime.date) for x in rows)


def test_starting_train_passed_mapping():
    rows = parse_starting_train(_read("tab_starting_train.html"))
    for x in rows:
        if x["remark"] and "불량" in x["remark"]:
            assert x["passed"] is False
        elif x["remark"] == "양호":
            assert x["passed"] is True


def test_weight_rows():
    rows = parse_weight(_read("tab_weight.html"))
    byno = {r["program_number"]: r for r in rows}
    assert byno[1]["horse_name"] == "파사퀸"
    assert byno[1]["today_weight"] == 485 and byno[1]["weight_delta"] == -3
    assert byno[1]["top3_avg"] == 490
    # '0' means no stat -> None (황금송 3위평균=0 in fixture)
    assert byno[2]["top3_avg"] is None


def test_train_state_sessions():
    rows = parse_train_state(_read("tab_train_state.html"))
    byno = {r["program_number"]: r for r in rows}
    assert byno[1]["horse_name"] == "파사퀸"
    assert len(byno[1]["sessions"]) >= 5
    s = byno[1]["sessions"][0]
    assert set(s) == {"day_label", "rider", "count"}
    assert isinstance(s["count"], int)


def test_accessory_medical():
    rows = parse_accessory_medical(_read("tab_accessory.html"))
    byno = {r["program_number"]: r for r in rows}
    assert byno[1]["horse_name"] == "파사퀸"
    assert any(m["record_date"] == datetime.date(2026, 6, 10) for m in byno[1]["medical"])
    assert isinstance(byno[1]["eiph"], bool)


def test_main_top3():
    rows = parse_main_top3(_read("main_seoul.html"))
    assert len(rows) >= 1
    r = rows[0]
    assert r["track_label"] in ("서울", "부경", "제주")
    assert isinstance(r["race_number"], int)
    assert len(r["fav_nums"]) == 3 and all(isinstance(n, int) for n in r["fav_nums"])
