"""Tests for joborion.sourcing.normalize — deterministic, LLM-free structuring."""

from joborion.sourcing.normalize import (
    NormalizedJob,
    annualize,
    extract_country_city,
    normalize_company,
    normalize_job,
    normalize_title,
    parse_job_type,
    parse_salary,
    parse_seniority,
    country_code_for,
)


class TestExtractCountryCity:
    def test_common_english_country_name(self):
        assert extract_country_city("London, United Kingdom") == ("GB", "London")

    def test_country_alone(self):
        assert extract_country_city("Germany") == ("DE", "")

    def test_alias_uk(self):
        assert extract_country_city("Remote, UK") == ("GB", "")

    def test_us_city_state_country(self):
        assert extract_country_city("San Francisco, CA, United States") == ("US", "San Francisco")

    def test_remote_only(self):
        assert extract_country_city("Remote") == ("", "")

    def test_empty(self):
        assert extract_country_city("") == ("", "")

    def test_country_alpha2_known_alias(self):
        assert extract_country_city("Berlin, Germany")[0] == "DE"

    def test_unknown_location(self):
        assert extract_country_city("Somewhere Else")[0] == ""


class TestCountryCodeFor:
    def test_full_name(self):
        assert country_code_for("Canada") == "CA"

    def test_alias(self):
        assert country_code_for("uk") == "GB"

    def test_unknown(self):
        assert country_code_for("Berlin") == ""


class TestParseSalary:
    def test_extracts_salary_and_country(self):
        low, high, currency, interval = parse_salary("$60,000 - $80,000/year", "")
        assert (low, high, currency, interval) == (60000.0, 80000.0, "USD", "annual")

    def test_k_notation_defaults_to_annual(self):
        low, high, currency, interval = parse_salary("$80k - $100k", "")
        assert (low, high, currency, interval) == (80000.0, 100000.0, "USD", "annual")

    def test_single_value(self):
        low, high, _, _ = parse_salary("$70k", "")
        assert (low, high) == (70000.0, 70000.0)

    def test_up_to_single(self):
        low, high, _, _ = parse_salary("Up to $90k", "")
        assert (low, high) == (None, 90000.0)

    def test_gbp_currency(self):
        _, _, currency, _ = parse_salary("£45k - £55k", "")
        assert currency == "GBP"

    def test_hourly_interval(self):
        low, high, _, interval = parse_salary("$30 - $40 per hour", "")
        assert interval == "hourly"

    def test_salary_from_description_when_text_missing(self):
        low, high, _, _ = parse_salary(None, "Salary: 50k-65k depending on experience")
        assert (low, high) == (50000.0, 65000.0)

    def test_no_salary(self):
        assert parse_salary(None, "We offer great benefits") == (None, None, "", "")


class TestParseJobType:
    def test_fulltime(self):
        assert parse_job_type("Full-time Software Engineer") == "fulltime"

    def test_parttime(self):
        assert parse_job_type("Part-time Barista") == "parttime"

    def test_contract(self):
        assert parse_job_type("Contract Developer") == "contract"

    def test_internship(self):
        assert parse_job_type("Summer Internship 2026") == "internship"

    def test_none(self):
        assert parse_job_type("Software Engineer") == ""

    def test_fulltime_beats_parttime_when_both(self):
        assert parse_job_type("Full-time or part-time role") == "fulltime"


class TestParseSeniority:
    def test_senior(self):
        assert parse_seniority("Senior Software Engineer") == "senior"

    def test_junior(self):
        assert parse_seniority("Junior Developer") == "entry"

    def test_staff(self):
        assert parse_seniority("Staff Engineer") == "staff"

    def test_lead(self):
        assert parse_seniority("Principal Engineer") == "lead"

    def test_none(self):
        assert parse_seniority("Software Engineer") == ""


class TestNormalizeTitle:
    def test_lowercases_and_sorts(self):
        assert normalize_title("Senior Software Engineer") == "engineer senior software"

    def test_ignores_punctuation_and_order(self):
        assert normalize_title("Software Engineer (Senior)") == "engineer senior software"

    def test_single_word(self):
        assert normalize_title("Python") == "python"


class TestNormalizeCompany:
    def test_strips_suffix(self):
        assert normalize_company("Acme Inc") == "acme"
        assert normalize_company("Stripe, LLC") == "stripe"

    def test_lowercases(self):
        assert normalize_company("OpenAI") == "openai"


class TestAnnualize:
    def test_hourly(self):
        assert annualize(50.0, "hourly") == 50.0 * 2080

    def test_monthly(self):
        assert annualize(5000.0, "monthly") == 60000.0

    def test_annual_passthrough(self):
        assert annualize(80000.0, "annual") == 80000.0


class TestNormalizeJob:
    def test_row_to_normalized(self):
        norm = normalize_job(
            {
                "url": "https://x.com/job",
                "title": "Senior Backend Engineer",
                "company": "Acme Inc",
                "location": "Remote, United Kingdom",
                "description": "Fully remote role building distributed systems",
                "salary": "$80k - $100k",
                "site": "remote_boards",
                "discovered_at": "2026-08-05T00:00:00+00:00",
                "application_url": "https://x.com/apply",
            }
        )
        assert isinstance(norm, NormalizedJob)
        assert norm.country == "GB"
        assert norm.city == ""
        assert norm.is_remote is True
        assert norm.salary_min == 80000.0
        assert norm.salary_max == 100000.0
        assert norm.salary_currency == "USD"
        assert norm.job_type == ""
        assert norm.seniority == "senior"
        assert norm.source_provider == "remote_boards"
        assert norm.apply_url_direct == "https://x.com/apply"
        assert norm.normalized_title == "backend engineer senior"
