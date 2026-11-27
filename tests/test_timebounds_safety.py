from datetime import date

import pytest
from sqlglot import dialects

from analytics_query_analyzer import analyze

SCHEMA = {"p": {"shop": {"orders": {"ordered_at": "date"}}}}


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("date_add(ordered_at, interval 1 day) >= '2026-01-01'", (None, None)),
        ("ordered_at in (date '2026-01-01', @unknown)", (None, None)),
        (
            "date_trunc(ordered_at, month) = '2026-01-01'",
            (date(2026, 1, 1), date(2026, 1, 31)),
        ),
    ],
)
def test_bounds_do_not_exclude_possible_dates(condition, expected):
    rows = analyze(
        dialects.BigQuery,
        f"select ordered_at from shop.orders where {condition}",
        SCHEMA,
        "p",
        with_timebounds=True,
    )
    assert (rows[0]["lower"], rows[0]["upper"]) == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            "with a as (select * from shop.orders where ordered_at >= '2026-01-01'), b as (select * from shop.orders) select a.ordered_at from a join b on true",
            (None, None),
        ),
        (
            "with a as (select ordered_at from shop.orders where ordered_at >= '2026-01-01' union all select ordered_at from shop.orders where ordered_at >= '2026-06-01') select * from a",
            (date(2026, 1, 1), None),
        ),
        (
            "with a as (select * from shop.orders where ordered_at between '2026-01-01' and '2026-01-31'), b as (select * from shop.orders where ordered_at between '2026-03-01' and '2026-03-31') select a.ordered_at from a join b on true",
            (date(2026, 1, 1), date(2026, 3, 31)),
        ),
        (
            "select ordered_at from shop.orders where ordered_at >= '2026-01-01' union all select ordered_at from shop.orders",
            (None, None),
        ),
        (
            "select ordered_at from (select ordered_at from shop.orders) x where ordered_at >= '2026-01-01'",
            (date(2026, 1, 1), None),
        ),
        (
            "select a.ordered_at from shop.orders a left join shop.orders b on a.ordered_at >= '2026-01-01'",
            (None, None),
        ),
    ],
)
def test_bounds_cover_each_table_read(sql, expected):
    rows = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)
    row = next(row for row in rows if row["column"] == "ordered_at")
    assert (row["lower"], row["upper"]) == expected


def test_reused_cte_filter_does_not_bound_both_reads():
    sql = "with a as (select ordered_at from shop.orders) select x.ordered_at from a x join a y on true where x.ordered_at >= '2026-01-01'"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["lower"] is None


def test_bigquery_date_diff_recent_days():
    sql = "select ordered_at from shop.orders where date_diff(current_date(), ordered_at, day) <= 7"
    row = analyze(
        dialects.BigQuery,
        sql,
        SCHEMA,
        "p",
        with_timebounds=True,
        current_date_provider=lambda: "2026-01-15",
    )[0]
    assert (row["lower"], row["upper"]) == (date(2026, 1, 8), None)


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (
            "date_trunc(ordered_at, month) <= date '2026-01-01'",
            (None, date(2026, 1, 31)),
        ),
        (
            "date_trunc(ordered_at, week) = date '2026-01-04'",
            (date(2026, 1, 4), date(2026, 1, 10)),
        ),
    ],
)
def test_truncated_column_boundaries_cover_whole_period(condition, expected):
    row = analyze(
        dialects.BigQuery,
        f"select ordered_at from shop.orders where {condition}",
        SCHEMA,
        "p",
        with_timebounds=True,
    )[0]
    assert (row["lower"], row["upper"]) == expected


def test_min_upper_bound_does_not_bound_all_rows():
    sql = "select min(ordered_at) as earliest from shop.orders having earliest <= date '2026-01-01'"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["upper"] is None


def test_outer_filter_on_aggregate_alias_does_not_bound_all_rows():
    sql = "select earliest from (select min(ordered_at) as earliest from shop.orders) x where earliest <= date '2026-01-01'"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["upper"] is None


def test_column_cast_to_string_is_not_treated_as_date_filter():
    sql = "select ordered_at from shop.orders where cast(ordered_at as string) = '2026-01-01'"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["upper"] is None and row["lower"] is None


def test_timestamp_literal_offset_uses_utc_calendar_date():
    schema = {"p": {"shop": {"events": {"occurred_at": "timestamp"}}}}
    sql = "select occurred_at from shop.events where occurred_at >= timestamp('2026-01-01 00:00:00+09:00')"
    row = analyze(dialects.BigQuery, sql, schema, "p", with_timebounds=True)[0]
    assert row["lower"] == date(2025, 12, 31)


def test_timestamp_to_date_with_zone_is_not_treated_as_identity():
    schema = {"p": {"shop": {"events": {"occurred_at": "timestamp"}}}}
    sql = "select occurred_at from shop.events where date(occurred_at, 'America/Los_Angeles') <= date '2026-01-01'"
    row = analyze(dialects.BigQuery, sql, schema, "p", with_timebounds=True)[0]
    assert row["upper"] is None


def test_current_date_respects_explicit_timezone_with_datetime_provider():
    from datetime import datetime, timezone

    sql = "select ordered_at from shop.orders where ordered_at >= current_date('Asia/Tokyo')"
    row = analyze(
        dialects.BigQuery,
        sql,
        SCHEMA,
        "p",
        with_timebounds=True,
        current_date_provider=lambda: datetime(2026, 1, 1, 16, tzinfo=timezone.utc),
    )[0]
    assert row["lower"] == date(2026, 1, 2)


def test_timestamp_trunc_with_timezone_does_not_assume_utc_boundary():
    schema = {"p": {"shop": {"events": {"occurred_at": "timestamp"}}}}
    sql = "select occurred_at from shop.events where timestamp_trunc(occurred_at, day, 'America/Los_Angeles') <= timestamp '2026-01-01 08:00:00+00'"
    row = analyze(dialects.BigQuery, sql, schema, "p", with_timebounds=True)[0]
    assert row["upper"] is None


def test_lag_window_filter_does_not_bound_all_rows():
    sql = "select ordered_at from shop.orders qualify lag(ordered_at) over (order by ordered_at) >= date '2026-01-01'"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["lower"] is None


@pytest.mark.parametrize(
    "condition",
    [
        "min(ordered_at) between date '2026-01-01' and date '2026-01-31'",
        "date_trunc(min(ordered_at), month) <= date '2026-01-01'",
        "cast(min(ordered_at) as date) <= date '2026-01-01'",
    ],
)
def test_aggregate_wrappers_do_not_bound_every_input_row(condition):
    sql = f"select min(ordered_at) from shop.orders having {condition}"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["upper"] is None


def test_default_current_date_evaluates_requested_timezone(monkeypatch):
    from datetime import datetime, timezone
    import analytics_query_analyzer.timebounds_analyzer as module

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 1, 16, tzinfo=timezone.utc)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)
    sql = "select ordered_at from shop.orders where ordered_at >= current_date('Asia/Tokyo')"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["lower"] == date(2026, 1, 2)


def test_union_of_two_uses_of_same_cte_preserves_both_ranges():
    sql = """
    with base as (select ordered_at from shop.orders)
    select ordered_at from base where ordered_at between date '2026-01-01' and date '2026-01-31'
    union all
    select ordered_at from base where ordered_at between date '2026-03-01' and date '2026-03-31'
    """
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert (row["lower"], row["upper"]) == (date(2026, 1, 1), date(2026, 3, 31))


def test_date_diff_with_datetime_column_uses_conservative_day_envelope():
    schema = {"p": {"shop": {"orders": {"ordered_at": "datetime"}}}}
    sql = "select ordered_at from shop.orders where date_diff(current_date(), ordered_at, day) <= 7"
    row = analyze(
        dialects.BigQuery,
        sql,
        schema,
        "p",
        with_timebounds=True,
        current_date_provider=lambda: "2026-01-15",
    )[0]
    assert (row["lower"], row["upper"]) == (date(2026, 1, 7), None)


def test_min_window_with_following_frame_does_not_bound_current_row():
    schema = {"p": {"shop": {"orders": {"id": "int64", "ordered_at": "date"}}}}
    sql = "select ordered_at from shop.orders qualify min(ordered_at) over (order by id rows between 1 following and 1 following) >= date '2026-01-01'"
    row = next(
        r
        for r in analyze(dialects.BigQuery, sql, schema, "p", with_timebounds=True)
        if r["column"] == "ordered_at"
    )
    assert row["lower"] is None


def test_date_trunc_minimum_week_does_not_raise():
    sql = "select ordered_at from shop.orders where date_trunc(ordered_at, week) = date '0001-01-01'"
    row = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)[0]
    assert row["lower"] is None and row["upper"] is None


@pytest.mark.parametrize(
    "literal", ["date(2026, 2, 30)", "date_add(date '9999-12-31', interval 1 day)"]
)
def test_invalid_or_out_of_range_date_expressions_do_not_crash(literal):
    row = analyze(
        dialects.BigQuery,
        f"select ordered_at from shop.orders where ordered_at >= {literal}",
        SCHEMA,
        "p",
        with_timebounds=True,
    )[0]
    assert row["lower"] is None
