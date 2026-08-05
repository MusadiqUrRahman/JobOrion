"""Tests for joborion.sourcing.query_evolution — LLM query expansion."""

import pytest

from joborion.database import init_db, close_connection
from joborion.sourcing.query_evolution import (
    _parse_queries_response,
    active_queries,
    expand_queries,
    mark_queries_used,
    record_query_passes,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


class TestParseQueriesResponse:
    def test_parses_pipe_lines(self):
        response = "python backend engineer|1\nreact developer|2\ndata platform engineer|1"
        queries = _parse_queries_response(response)
        assert queries == [
            {"query": "python backend engineer", "tier": 1},
            {"query": "react developer", "tier": 2},
            {"query": "data platform engineer", "tier": 1},
        ]

    def test_ignores_garbage_lines(self):
        response = "QUERIES:\npython|1\n\nunparsable line here\n"
        queries = _parse_queries_response(response)
        assert queries == [{"query": "python", "tier": 1}]

    def test_clamps_tier_out_of_range(self):
        response = "python|9\njava|-1\nruby|0"
        queries = _parse_queries_response(response)
        assert {q["query"]: q["tier"] for q in queries} == {
            "python": 3,
            "java": 1,
            "ruby": 1,
        }

    def test_empty_response(self):
        assert _parse_queries_response("") == []


class TestExpandQueries:
    def test_expands_queries_from_fit(self, conn):
        conn.execute(
            """INSERT INTO jobs (url, title, fit_score) VALUES
               ('https://a/1', 'Senior Python Engineer', 9),
               ('https://a/2', 'Machine Learning Engineer', 8)"""
        )
        conn.commit()

        calls = {}

        class _FakeClient:
            def chat(self, messages, max_tokens, temperature):
                calls["messages"] = messages
                calls["temperature"] = temperature
                return "python backend engineer|1\ndistributed systems|2"

        evolved = expand_queries(conn, client=_FakeClient())

        assert [q["query"] for q in evolved] == ["python backend engineer", "distributed systems"]
        user_content = calls["messages"][-1]["content"]
        assert "Senior Python Engineer" in user_content
        assert "Machine Learning Engineer" in user_content
        row = conn.execute(
            "SELECT query, tier, origin FROM query_history WHERE query='python backend engineer'"
        ).fetchone()
        assert row is not None
        assert row["tier"] == 1
        assert row["origin"] == "llm"

    def test_no_fit_jobs_skips_llm(self, conn):
        class _FakeClient:
            def chat(self, messages, max_tokens, temperature):
                raise AssertionError("LLM must not be called without fit jobs")

        assert expand_queries(conn, client=_FakeClient()) == []

    def test_stores_and_returns_new_queries(self, conn):
        conn.execute(
            """INSERT INTO jobs (url, title, fit_score) VALUES ('https://a/1', 'Python Engineer', 7)"""
        )
        conn.commit()

        class _FakeClient:
            def chat(self, messages, max_tokens, temperature):
                return "python|1\nfastapi|1"

        expand_queries(conn, client=_FakeClient())
        expanded_again = expand_queries(conn, client=_FakeClient())

        assert len(expanded_again) == 0


class TestActiveQueries:
    def test_rotates_unused_first_then_lru(self, conn):
        conn.executemany(
            """INSERT INTO query_history (query, tier, used_at) VALUES (?, ?, ?)""",
            [
                ("old-used", 1, "2026-01-01T00:00:00"),
                ("fresh-new", 1, None),
                ("mid-used", 2, "2026-01-02T00:00:00"),
            ],
        )
        conn.commit()
        assert [q["query"] for q in active_queries(conn)] == [
            "fresh-new", "old-used", "mid-used",
        ]

    def test_respects_limit(self, conn):
        conn.executemany(
            """INSERT INTO query_history (query, tier) VALUES (?, 1)""",
            [("q1",), ("q2",), ("q3",)],
        )
        conn.commit()
        assert [q["query"] for q in active_queries(conn, limit=2)] == ["q1", "q2"]

    def test_empty_history(self, conn):
        assert active_queries(conn) == []


class TestQueryUsage:
    def test_mark_queries_used(self, conn):
        conn.executemany(
            """INSERT INTO query_history (query) VALUES (?)""",
            [("python",), ("java",)],
        )
        conn.commit()
        mark_queries_used(conn, [{"query": "python", "tier": 1}])
        used = conn.execute(
            "SELECT used_at FROM query_history WHERE query='python'"
        ).fetchone()
        assert used["used_at"] is not None

    def test_record_query_passes(self, conn):
        conn.execute("INSERT INTO query_history (query) VALUES ('python')")
        conn.commit()
        record_query_passes(conn, [{"query": "python", "tier": 1}], passed=3)
        row = conn.execute(
            "SELECT last_passed FROM query_history WHERE query='python'"
        ).fetchone()
        assert row["last_passed"] == 3
