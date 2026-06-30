"""Tests for scanner tag-parsing helpers."""
import scanner


def test_first_handles_scalars_and_lists():
    assert scanner._first(None) is None
    assert scanner._first("hi") == "hi"
    assert scanner._first(["a", "b"]) == "a"
    assert scanner._first([]) is None
    assert scanner._first(5) == "5"


def test_parse_track_no():
    assert scanner._parse_track_no(["3/12"]) == 3
    assert scanner._parse_track_no(["5"]) == 5
    assert scanner._parse_track_no("7/9") == 7
    assert scanner._parse_track_no(None) is None
    assert scanner._parse_track_no(["abc"]) is None


def test_parse_year():
    assert scanner._parse_year(["2020-01-01"]) == 2020
    assert scanner._parse_year(["1999"]) == 1999
    assert scanner._parse_year(["1987-08"]) == 1987
    assert scanner._parse_year(None) is None
    assert scanner._parse_year(["no-year-here"]) is None
