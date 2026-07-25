"""Tests for RunReporter — formatted run summary reports."""

from joborion.agent.reporter import RunReporter


class TestRunReporter:
    def setup_method(self):
        self.reporter = RunReporter()

    def test_generate_full_report(self):
        data = {
            "goal": "Find Python jobs",
            "duration_s": 45.2,
            "total_cost": 0.0123,
            "stages": [
                {"name": "search", "count": 10, "status": "ok"},
                {"name": "score", "count": 10, "status": "ok"},
            ],
            "top_jobs": [
                {"title": "Python Dev", "company": "Acme", "score": 9},
            ],
            "errors": ["Tool search_workday failed"],
            "lessons": ["Consider blocking workday"],
        }
        report = self.reporter.generate(data)
        assert "JobOrion Run Report" in report
        assert "Find Python jobs" in report
        assert "45.2s" in report
        assert "$0.0123" in report
        assert "Python Dev" in report
        assert "search_workday failed" in report
        assert "Consider blocking workday" in report

    def test_generate_empty_data(self):
        report = self.reporter.generate({})
        assert "JobOrion Run Report" in report
        assert "$0.0000" in report

    def test_format_duration_seconds(self):
        assert self.reporter._format_duration(30.5) == "30.5s"

    def test_format_duration_minutes(self):
        assert self.reporter._format_duration(90) == "1m 30s"

    def test_format_duration_hours(self):
        assert self.reporter._format_duration(3661) == "1h 1m 1s"

    def test_generate_no_stages(self):
        data = {"goal": "test", "stages": []}
        report = self.reporter.generate(data)
        assert "Pipeline:" not in report

    def test_generate_no_errors(self):
        data = {"goal": "test", "errors": []}
        report = self.reporter.generate(data)
        assert "Errors:" not in report

    def test_generate_no_lessons(self):
        data = {"goal": "test", "lessons": []}
        report = self.reporter.generate(data)
        assert "Lessons learned:" not in report

    def test_generate_top_jobs_limited(self):
        data = {
            "goal": "test",
            "top_jobs": [{"title": f"Job {i}", "company": "Co", "score": i} for i in range(10)],
        }
        report = self.reporter.generate(data)
        assert "Job 4" in report
        assert "Job 5" not in report
