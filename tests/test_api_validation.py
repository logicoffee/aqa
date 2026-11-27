import pytest
from sqlglot import dialects

from analytics_query_analyzer import analyze, build_schema

SCHEMA = {"p": {"shop": {"orders": {"id": "int64"}}}}


def test_string_dialect_matches_class():
    assert analyze("bigquery", "select id from shop.orders", SCHEMA, "p") == analyze(
        dialects.BigQuery, "select id from shop.orders", SCHEMA, "p"
    )


def test_build_schema_resolves_string_dialect_before_dispatch(monkeypatch):
    import analytics_query_analyzer.schema_builder as module

    monkeypatch.setattr(module, "_build_schema_bigquery", lambda *args: {"ok": args})
    assert build_schema("bigquery", "p") == {"ok": ("p", None, None)}


def test_multiple_statements_are_rejected():
    with pytest.raises(ValueError, match="single"):
        analyze(
            dialects.BigQuery,
            "DECLARE x INT64 DEFAULT 1; SELECT id FROM shop.orders",
            SCHEMA,
            "p",
        )


def test_count_star_reports_table_without_a_column():
    assert analyze("bigquery", "select count(*) from shop.orders", SCHEMA, "p") == [
        {"database": "p", "schema": "shop", "table": "orders", "column": None}
    ]


def test_table_without_column_is_included_with_other_references():
    schema = {"p": {"shop": {"orders": {"id": "int64"}, "users": {"id": "int64"}}}}
    rows = analyze(
        "bigquery",
        "select o.id from shop.orders o cross join shop.users u",
        schema,
        "p",
    )
    assert {(r["table"], r["column"]) for r in rows} == {
        ("orders", "id"),
        ("users", None),
    }
