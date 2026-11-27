from datetime import date

from sqlglot import dialects
from analytics_query_analyzer import analyze

SCHEMA = {
    "p": {
        "shop": {
            "events_20260101": {"id": "int64", "ordered_at": "date"},
            "events_20260102": {"id": "int64", "ordered_at": "date"},
            "orders": {"id": "int64"},
        }
    }
}


def test_wildcard_table_columns_are_resolved():
    rows = analyze(
        dialects.BigQuery,
        "select id from `p.shop.events_*` where _TABLE_SUFFIX = '20260101'",
        SCHEMA,
        "p",
        with_timebounds=True,
    )
    assert {(r["table"], r["column"]) for r in rows} == {
        ("events_*", "id"),
        ("events_*", "_table_suffix"),
    }


def test_partition_pseudocolumn_has_bounds():
    rows = analyze(
        dialects.BigQuery,
        "select id from shop.orders where _PARTITIONDATE >= date '2026-01-01'",
        SCHEMA,
        "p",
        with_timebounds=True,
    )
    row = next(r for r in rows if r["column"].lower() == "_partitiondate")
    assert row["lower"] == date(2026, 1, 1)
    assert "_PARTITIONDATE" not in SCHEMA["p"]["shop"]["orders"]


def test_star_does_not_include_pseudocolumn():
    rows = analyze(
        dialects.BigQuery,
        "select * from shop.orders where _PARTITIONDATE >= date '2026-01-01'",
        SCHEMA,
        "p",
    )
    assert {row["column"] for row in rows} == {"id", "_partitiondate"}


def test_table_suffix_bounds_preserve_strings():
    rows = analyze(
        dialects.BigQuery,
        "select id from `p.shop.events_*` where _TABLE_SUFFIX >= '20260101' and _TABLE_SUFFIX < '20260201'",
        SCHEMA,
        "p",
        with_timebounds=True,
    )
    row = next(r for r in rows if r["column"] == "_table_suffix")
    assert (row["lower"], row["upper"]) == ("20260101", "20260201")


def test_table_suffix_between_and_in():
    for condition, expected in [
        ("between '20260101' and '20260131'", ("20260101", "20260131")),
        ("in ('20260105', '20260101')", ("20260101", "20260105")),
    ]:
        rows = analyze(
            dialects.BigQuery,
            f"select id from `p.shop.events_*` where _TABLE_SUFFIX {condition}",
            SCHEMA,
            "p",
            with_timebounds=True,
        )
        row = next(r for r in rows if r["column"] == "_table_suffix")
        assert (row["lower"], row["upper"]) == expected


def test_explicit_column_on_wildcard_without_matching_schema():
    schema = {"p": {"shop": {"orders": {"id": "int64"}}}}
    rows = analyze(dialects.BigQuery, "select id from `p.shop.events_*`", schema, "p")
    assert rows == [
        {"database": "p", "schema": "shop", "table": "events_*", "column": "id"}
    ]


def test_empty_dataset_schema_allows_explicit_table_references():
    rows = analyze(
        dialects.BigQuery, "select id from `p.shop.events_*`", {"p": {"shop": {}}}, "p"
    )
    assert rows[0]["table"] == "events_*" and rows[0]["column"] == "id"


def test_partition_pseudocolumn_is_not_added_to_other_tables_star():
    schema = {"p": {"shop": {"orders": {"id": "int64"}, "users": {"id": "int64"}}}}
    sql = "select * from shop.orders where id in (select id from shop.users where _PARTITIONDATE >= date '2026-01-01')"
    rows = analyze(dialects.BigQuery, sql, schema, "p")
    assert {(r["table"], r["column"]) for r in rows} == {
        ("orders", "id"),
        ("users", "id"),
        ("users", "_partitiondate"),
    }


def test_nested_struct_first_in_schema_supports_time_bounds():
    schema = {"p": {"shop": {"orders": {"event": {"at": "date"}, "id": "int64"}}}}
    sql = "select event.at from shop.orders where event.at >= date '2026-01-01'"
    rows = analyze(dialects.BigQuery, sql, schema, "p", with_timebounds=True)
    row = next(r for r in rows if r["column"] == "event.at")
    assert row["lower"] == date(2026, 1, 1)


def test_partition_pseudocolumn_works_without_table_schema():
    sql = "select _PARTITIONDATE from `p.shop.unknown` where _PARTITIONDATE >= date '2026-01-01'"
    row = analyze(
        dialects.BigQuery, sql, {"p": {"shop": {}}}, "p", with_timebounds=True
    )[0]
    assert row["column"] == "_partitiondate" and row["lower"] == date(2026, 1, 1)


def test_wildcard_schema_includes_fields_from_each_matching_table():
    schema = {
        "p": {
            "shop": {
                "events_1": {"old_field": "int64"},
                "events_2": {"new_field": "int64"},
            }
        }
    }
    rows = analyze(dialects.BigQuery, "select * from `p.shop.events_*`", schema, "p")
    assert {row["column"] for row in rows} == {"old_field", "new_field"}


def test_table_suffix_can_use_format_date_with_current_date():
    sql = "select id from `p.shop.events_*` where _table_suffix between format_date('%Y%m%d', date_sub(current_date(), interval 7 day)) and format_date('%Y%m%d', current_date())"
    rows = analyze(
        dialects.BigQuery,
        sql,
        SCHEMA,
        "p",
        with_timebounds=True,
        current_date_provider=lambda: "2026-01-15",
    )
    row = next(r for r in rows if r["column"] == "_table_suffix")
    assert (row["lower"], row["upper"]) == ("20260108", "20260115")


def test_partitiontime_bounds_are_inferred():
    sql = "select id from shop.orders where _PARTITIONTIME >= timestamp '2026-01-01 00:00:00+00'"
    rows = analyze(dialects.BigQuery, sql, SCHEMA, "p", with_timebounds=True)
    row = next(r for r in rows if r["column"] == "_partitiontime")
    assert row["lower"] == date(2026, 1, 1)


def test_suffix_bounds_without_concrete_table_schema():
    sql = "select id from `p.shop.events_*` where _table_suffix between '20260101' and '20260131'"
    rows = analyze(
        dialects.BigQuery, sql, {"p": {"shop": {}}}, "p", with_timebounds=True
    )
    row = next(r for r in rows if r["column"] == "_table_suffix")
    assert (row["lower"], row["upper"]) == ("20260101", "20260131")


def test_wildcard_incompatible_types_do_not_create_time_bounds():
    schema = {
        "p": {"shop": {"events_1": {"value": "date"}, "events_2": {"value": "string"}}}
    }
    sql = "select value from `p.shop.events_*` where value >= '2026-01-01'"
    rows = analyze(dialects.BigQuery, sql, schema, "p", with_timebounds=True)
    assert (rows[0]["lower"], rows[0]["upper"]) == (None, None)
