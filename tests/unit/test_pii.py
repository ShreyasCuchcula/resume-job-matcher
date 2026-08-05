"""Unit tests for parsing/pii.py (SPECIFICATION.md Section 9.4)."""

from __future__ import annotations

from parsing.pii import mask_person_entities, strip_pii_from_lines, strip_pii_regex


def test_email_stripped():
    assert "[REDACTED]" in strip_pii_regex("Contact: jordan.ellis@example.com")
    assert "jordan.ellis@example.com" not in strip_pii_regex(
        "Contact: jordan.ellis@example.com"
    )


def test_phone_number_stripped():
    result = strip_pii_regex("Call me at (555) 010-1001 today.")
    assert "555" not in result
    assert "1001" not in result


def test_international_phone_stripped():
    result = strip_pii_regex("Phone: +1-555-010-1001")
    assert "1001" not in result


def test_url_and_social_handle_stripped():
    result = strip_pii_regex("Visit https://linkedin.com/in/jordanellis for more.")
    assert "linkedin.com" not in result


def test_street_address_stripped():
    result = strip_pii_regex("I live at 123 Main Street, Springfield.")
    assert "123 Main Street" not in result
    assert "Springfield" in result  # city name is not PII by itself


def test_dob_stripped():
    result = strip_pii_regex("DOB: 01/15/1990")
    assert "1990" not in result


def test_age_stripped():
    assert "34" not in strip_pii_regex("Age: 34")


def test_gender_stripped():
    assert "Male" not in strip_pii_regex("Gender: Male")


def test_pronouns_stripped():
    assert "She/Her" not in strip_pii_regex("Pronouns: She/Her")


def test_marital_status_stripped():
    assert "Married" not in strip_pii_regex("Marital Status: Married")


def test_nationality_stripped():
    assert "American" not in strip_pii_regex("Nationality: American")


def test_ordinary_text_untouched():
    text = "Built and maintained recurring Power BI dashboards for merchandising stakeholders."
    assert strip_pii_regex(text) == text


def test_city_state_location_not_treated_as_address():
    """A bare "City, ST" location (no street) must survive - only a
    literal street address gets redacted."""
    assert strip_pii_regex("Columbus, OH") == "Columbus, OH"


def test_employment_dates_not_mistaken_for_phone_numbers():
    text = "Data Analyst - Acme Corp (Jun 2022 - Present)"
    assert strip_pii_regex(text) == text


class TestMaskPersonEntities:
    def test_masks_a_name(self):
        result = mask_person_entities(
            "Charlie Fenwick is a data engineer with three years of experience."
        )
        assert "Charlie" not in result
        assert "Fenwick" not in result

    def test_does_not_mask_company_names(self):
        result = mask_person_entities("Worked at Bayline Data Co. building pipelines.")
        assert "Bayline Data Co." in result

    def test_does_not_mask_ordinary_technical_text(self):
        text = "Wrote SQL queries against the warehouse and built Power BI dashboards."
        assert mask_person_entities(text) == text

    def test_empty_text_returns_empty(self):
        assert mask_person_entities("") == ""


class TestStripPiiFromLines:
    def test_preserves_line_count(self):
        lines = [
            "Jordan Ellis",
            "jordan.ellis@example.com | (555) 010-1001 | Columbus, OH",
            "SUMMARY",
        ]
        result = strip_pii_from_lines(lines)
        assert len(result) == len(lines)

    def test_name_and_contact_both_removed(self):
        lines = [
            "Charlie Fenwick",
            "charlie@example.com | (555) 010-1010 | San Jose, CA",
        ]
        result = strip_pii_from_lines(lines)
        joined = "\n".join(result)
        assert "Charlie" not in joined
        assert "charlie@example.com" not in joined
        assert "San Jose" in joined  # location itself is retained

    def test_empty_list_returns_empty_list(self):
        assert strip_pii_from_lines([]) == []
