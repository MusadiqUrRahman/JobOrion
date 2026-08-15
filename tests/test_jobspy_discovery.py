"""Tests for joborion.discovery.jobspy location/remote filtering."""

from unittest.mock import patch

import pandas as pd
import pytest

from joborion.database import init_db
from joborion.discovery import jobspy as jm


def _row(is_remote=None, location="United States"):
    r = {}
    if is_remote is not None:
        r["is_remote"] = is_remote
    if location is not None:
        r["location"] = location
    return r


class TestIsRemote:
    def test_true_when_board_flags_remote(self):
        assert jm._is_remote(_row(is_remote=True, location="United States")) is True

    def test_false_when_board_flags_onsite(self):
        assert jm._is_remote(_row(is_remote=False, location="New York, NY")) is False

    def test_remembers_missing_flag_and_location_text(self):
        assert jm._is_remote(_row(location="Remote (anywhere)")) is True
        assert jm._is_remote(_row(location="London, UK")) is False

    def test_na_flag_falls_back_to_location(self):
        assert jm._is_remote(_row(is_remote="nan", location="Work From Home")) is True


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "t.db"
    with patch("joborion.database.DB_PATH", str(db_path)):
        init_db(str(db_path))
        yield str(db_path)


class TestRunOneSearchLocationFilter:
    def test_remote_flagged_jobs_survive_plain_locations(self, monkeypatch, db):
        df = pd.DataFrame(
            [
                {"title": "AI Engineer", "company": "Acme", "location": "United States",
                 "is_remote": True, "job_url": "https://a/1", "description": "x", "site": "indeed"},
                {"title": "Onsite Dev", "company": "Acme", "location": "New York, NY",
                 "is_remote": False, "job_url": "https://a/2", "description": "x", "site": "indeed"},
            ]
        )
        search = {"query": "AI engineer", "location": "usa", "remote": True, "tier": 1}

        with patch.object(jm, "scrape_jobs", return_value=df) as m:
            result = jm._run_one_search(
                search, ["indeed"], 50, 168, None, {}, 0,
                ["remote", "worldwide"], [], {}, remote_only=True,
            )
        assert m.call_count == 1
        assert result["new"] == 1, result
        assert result["filtered"] == 1, result

    def test_remote_flagged_jobs_survive_worldwide_mode(self, monkeypatch, db):
        df = pd.DataFrame(
            [
                {"title": "LLM Engineer", "company": "Acme", "location": "Texas, US",
                 "is_remote": True, "job_url": "https://a/3", "description": "x", "site": "linkedin"},
            ]
        )
        search = {"query": "LLM engineer", "location": "worldwide", "remote": True, "tier": 1}

        with patch.object(jm, "scrape_jobs", return_value=df) as m:
            result = jm._run_one_search(
                search, ["linkedin"], 50, 168, None, {}, 0,
                ["remote", "worldwide"], [], {}, remote_only=True,
            )
        assert m.call_count == 1
        assert result["new"] == 1, result
