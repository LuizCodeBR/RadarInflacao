from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from radar_inflacao.analysis import (
    compare_periods,
    format_points,
    format_rate,
    reference_period,
    summarize_period,
)
from radar_inflacao.errors import ValidationError


def make_rows(values, start="2024-01"):
    from radar_inflacao.model import next_month

    return [
        {
            "period": next_month(start, index),
            "monthly": Decimal(value),
            "year_to_date": Decimal("7.654321"),
            "twelve_month": Decimal("9.876543"),
        }
        for index, value in enumerate(values)
    ]


def test_compounding_not_sum_and_official_windows_are_preserved():
    rows = make_rows(["1", "1"])
    original = deepcopy(rows)
    result = summarize_period(rows, "2024-01", "2024-02")
    assert result.compounded == Decimal("2.01")
    assert result.year_to_date == Decimal("7.654321")
    assert result.twelve_month == Decimal("9.876543")
    assert rows == original


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["0"], "0"),
        (["-0.5"], "-0.5"),
        (["-1", "1"], "-0.01"),
        (["-100", "2"], "-100"),
        (["0.42", "0.83", "0.16"], "1.4154915776"),
    ],
)
def test_zero_deflation_single_month_and_known_product(values, expected):
    rows = make_rows(values)
    result = summarize_period(rows, rows[0]["period"], rows[-1]["period"])
    assert result.compounded == Decimal(expected)


def test_calculation_ignores_callers_decimal_precision_and_sorts_without_mutation():
    rows = make_rows(["0.123456", "0.654321", "0.000001"])
    rows.reverse()
    original = deepcopy(rows)
    with localcontext() as context:
        context.prec = 6
        result = summarize_period(rows, "2024-01", "2024-03")
        assert context.prec == 6
    with localcontext() as context:
        context.prec = 80
        expected = (Decimal("1.00123456") * Decimal("1.00654321")
                    * Decimal("1.00000001") - 1) * 100
    assert result.compounded == expected
    assert rows == original


@pytest.mark.parametrize(
    ("start", "end", "mode", "expected"),
    [
        ("2024-01", "2024-03", "previous", ("2023-10", "2023-12")),
        ("2024-11", "2025-02", "previous", ("2024-07", "2024-10")),
        ("2024-12", "2024-12", "previous", ("2024-11", "2024-11")),
        ("2024-11", "2025-02", "year", ("2023-11", "2024-02")),
    ],
)
def test_reference_ranges_cross_years(start, end, mode, expected):
    assert reference_period(start, end, mode) == expected


@pytest.mark.parametrize(
    ("start", "end", "mode"),
    [("2024-03", "2024-01", "previous"), ("wrong", "2024-01", "year"),
     ("2024-01", "2024-02", "unknown")],
)
def test_invalid_reference_ranges_fail(start, end, mode):
    with pytest.raises(ValidationError):
        reference_period(start, end, mode)


@pytest.mark.parametrize("problem", ["empty", "missing", "duplicate", "outside"])
def test_incomplete_coverage_is_never_shortened_or_filled_with_zero(problem):
    rows = make_rows(["1", "2", "3"])
    start, end = "2024-01", "2024-03"
    if problem == "empty":
        rows = []
    elif problem == "missing":
        del rows[1]
    elif problem == "duplicate":
        rows.append(rows[0].copy())
    else:
        start = "2023-12"
    with pytest.raises(ValidationError, match="cobertura completa"):
        summarize_period(rows, start, end)


@pytest.mark.parametrize(
    "value",
    [None, 0.5, "0.5", Decimal("NaN"), Decimal("Infinity"),
     Decimal("-100.000001"), Decimal("1000000")],
)
def test_invalid_rates_are_rejected(value):
    rows = make_rows(["1"])
    rows[0]["monthly"] = value
    with pytest.raises(ValidationError, match="taxas decimais válidas"):
        summarize_period(rows, "2024-01", "2024-01")


def test_missing_official_value_is_not_hidden_by_valid_monthly_rate():
    rows = make_rows(["1"])
    del rows[0]["twelve_month"]
    with pytest.raises(ValidationError):
        summarize_period(rows, "2024-01", "2024-01")


def test_comparison_uses_signed_points_and_reports_length_and_overlap():
    rows = make_rows(["1", "1", "2"])
    result = compare_periods(rows, "2024-01", "2024-02", "2024-03", "2024-03")
    assert result.measures[0].difference == Decimal("0.01")
    assert result.measures[1].difference == Decimal("-1")
    assert result.a.count == 2 and result.b.count == 1
    assert not result.same_length
    assert not result.overlap
    shared = compare_periods(rows, "2024-01", "2024-02", "2024-02", "2024-03")
    assert shared.same_length and shared.overlap


def test_identical_periods_have_exact_zero_differences():
    rows = make_rows(["0.123456", "-0.005"])
    result = compare_periods(rows, "2024-01", "2024-02", "2024-01", "2024-02")
    assert result.same_length and result.overlap
    assert all(measure.difference == 0 for measure in result.measures)


@pytest.mark.parametrize(
    ("value", "rate", "points"),
    [
        ("0", "0,00%", "0,00 p.p."),
        ("-0.004", "0,00%", "0,00 p.p."),
        ("0.005", "0,01%", "+0,01 p.p."),
        ("-0.005", "-0,01%", "-0,01 p.p."),
        ("2.01", "2,01%", "+2,01 p.p."),
    ],
)
def test_display_rounding_sign_and_negative_zero(value, rate, points):
    assert format_rate(Decimal(value)) == rate
    assert format_points(Decimal(value)) == points


def test_comparison_uses_real_sample_and_keeps_official_accumulated_values(pipeline, repository):
    pipeline.demo()
    rows = repository.snapshot()["rows"]
    comparison = compare_periods(rows, "2024-01", "2024-03", "2023-01", "2023-03")
    assert comparison.a.compounded == Decimal("1.4154915776")
    assert comparison.a.year_to_date == Decimal("1.42")
    assert comparison.a.twelve_month == Decimal("3.93")
    assert comparison.a.monthly == Decimal("0.16")
