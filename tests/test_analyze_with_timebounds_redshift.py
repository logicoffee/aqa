from datetime import date

import pytest
from sqlglot import dialects

from analytics_query_analyzer.analyzer import analyze

schema = {
    "production": {
        "shop": {
            "orders": {"id": "int64", "ordered_at": "timestamp", "user_id": "int64"},
            "events": {"id": "int64", "event_at": "timestamp", "user_id": "int64"},
            "users": {"id": "int64", "name": "string"},
        }
    }
}

test_cases = [
    {
        "name": "without condition",
        "sql": "select ordered_at from shop.orders",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": None,
            }
        ],
    },
    {
        "name": "lower bound (>)",
        "sql": "select * from shop.orders where ordered_at > '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "lower bound (>=)",
        "sql": "select * from shop.orders where ordered_at >= '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "upper bound (<)",
        "sql": "select * from shop.orders where ordered_at < '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": date(2026, 1, 1),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "upper bound (<=)",
        "sql": "select * from shop.orders where ordered_at <= '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": date(2026, 1, 1),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "equality",
        "sql": "select * from shop.orders where ordered_at = '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": date(2026, 1, 1),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "in clause",
        "sql": "select * from shop.orders where ordered_at in ('2026-01-01')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": date(2026, 1, 1),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "between",
        "sql": "select * from shop.orders where ordered_at between '2026-01-01' and "
        "'2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": date(2026, 1, 2),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "trunc column",
        "sql": "select * from shop.orders where date_trunc('month', ordered_at) >= "
        "'2026-02-10'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 2, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "date function string",
        "sql": "select * from shop.orders where ordered_at >= to_date('2026-01-01', "
        "'YYYY-MM-DD')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "date from parts",
        "sql": "select * from shop.orders where ordered_at >= date_from_parts(2026, 1, 1)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "date literal",
        "sql": "select * from shop.orders where ordered_at >= date '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "datetime function string",
        "sql": "select * from shop.orders where ordered_at >= to_timestamp('2026-01-01 "
        "09:00:00', 'YYYY-MM-DD HH24:MI:SS')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "datetime from parts",
        "sql": "select * from shop.orders where ordered_at >= make_timestamp(2026, 1, 1, 9, "
        "0, 0)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "datetime literal",
        "sql": "select * from shop.orders where ordered_at >= cast('2026-01-01 09:00:00' as "
        "timestamp)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "timestamp function string",
        "sql": "select * from shop.orders where ordered_at >= to_timestamp('2026-01-01 "
        "09:00:00', 'YYYY-MM-DD HH24:MI:SS')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "timestamp function string with offset",
        "sql": "select * from shop.orders where ordered_at >= to_timestamp('2026-01-01 "
        "00:00:00+09:00', 'YYYY-MM-DD HH24:MI:SSOF')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2025, 12, 31),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "timestamp function zone",
        "sql": "select * from shop.orders where ordered_at >= timestamp '2026-01-01 "
        "00:00:00+09:00'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2025, 12, 31),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "timestamp literal",
        "sql": "select * from shop.orders where ordered_at >= timestamp '2026-01-01 "
        "09:00:00'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "timestamp from date",
        "sql": "select * from shop.orders where ordered_at >= timestamp(date '2026-01-01')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "date sub day",
        "sql": "select * from shop.orders where ordered_at > dateadd(day, -3, date "
        "'2026-01-04')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "interval sub day",
        "sql": "select * from shop.orders where ordered_at > (date '2026-01-04' - interval "
        "'3 day')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "date add day",
        "sql": "select * from shop.orders where ordered_at >= dateadd(day, 2, date "
        "'2026-01-04')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 6),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "interval add day",
        "sql": "select * from shop.orders where ordered_at >= (date '2026-01-04' + interval "
        "'2 day')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 6),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "date add month",
        "sql": "select * from shop.orders where ordered_at >= dateadd(month, 1, date "
        "'2026-01-31')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 2, 28),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "trunc literal",
        "sql": "select * from shop.orders where ordered_at >= date_trunc('month', "
        "'2026-02-10')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 2, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "cast date",
        "sql": "select * from shop.orders where ordered_at >= cast('2026-01-01' as date)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "cast datetime",
        "sql": "select * from shop.orders where ordered_at >= cast('2026-01-01 09:00:00' as "
        "timestamp)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "cast timestamp",
        "sql": "select * from shop.orders where ordered_at >= cast('2026-01-01 09:00:00' as "
        "timestamptz)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "timestamp seconds",
        "sql": "select * from shop.orders where ordered_at >= to_timestamp(1767229200)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "timestamp millis",
        "sql": "select * from shop.orders where ordered_at >= to_timestamp(1767229200.0)",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "parse date",
        "sql": "select * from shop.orders where ordered_at >= to_date('2026-01-01', "
        "'YYYY-MM-DD')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "parse datetime",
        "sql": "select * from shop.orders where ordered_at >= to_timestamp('2026-01-01 "
        "09:00:00', 'YYYY-MM-DD HH24:MI:SS')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "parse timestamp",
        "sql": "select * from shop.orders where ordered_at >= to_timestamp('2026-01-01 "
        "09:00:00+09:00', 'YYYY-MM-DD HH24:MI:SSOF')",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "differently formatted literals",
        "sql": "select * from shop.orders where ordered_at >= '2026-01-01' and ordered_at > "
        "'2026-01-02 09:00:00'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 2),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "non-literal",
        "sql": "select * from shop.orders where ordered_at > dateadd(month, -1, "
        "to_date('2026-01-01', 'YYYY-MM-DD'))",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2025, 12, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "not equal",
        "sql": "select * from shop.orders where ordered_at != '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "not equal (alt)",
        "sql": "select * from shop.orders where ordered_at <> '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "negation",
        "sql": "select * from shop.orders where not ordered_at > '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": date(2026, 1, 1),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "multiple conditions (and)",
        "sql": "select * from orders where ordered_at > '2026-01-01' and ordered_at > "
        "'2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 2),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "multiple conditions (or)",
        "sql": "select * from shop.orders where ordered_at > '2026-01-01' or ordered_at > "
        "'2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "lower > upper",
        "sql": "select * from shop.orders where ordered_at > '2026-01-02' and ordered_at < "
        "'2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "lower > upper between",
        "sql": "select * from shop.orders where ordered_at between '2026-01-02' and "
        "'2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "function wrapped column",
        "sql": "select * from shop.orders where date(ordered_at) >= '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "function wrapped mixed conditions",
        "sql": "select * from shop.orders where date(ordered_at) >= '2026-01-01' and "
        "ordered_at < '2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": date(2026, 1, 2),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "join condition",
        "sql": "select * from shop.users join shop.orders on users.id = orders.user_id and "
        "orders.ordered_at > '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "name",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "multiple tables",
        "sql": "select * from shop.orders join shop.events on orders.user_id = "
        "events.user_id where orders.ordered_at >= '2026-01-01' and events.event_at > "
        "'2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "events",
                "column": "event_at",
                "lower": date(2026, 1, 2),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "events",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "events",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "cte",
        "sql": "with base as (select ordered_at from shop.orders) select * from base where "
        "ordered_at > '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            }
        ],
    },
    {
        "name": "cte inner and outer",
        "sql": "with base as (select ordered_at from shop.orders where ordered_at >= "
        "'2026-01-01') select * from base where ordered_at < '2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": date(2026, 1, 2),
            }
        ],
    },
    {
        "name": "multi cte",
        "sql": "with base as (select ordered_at from shop.orders), filtered as (select "
        "ordered_at from base where ordered_at >= '2026-01-01') select * from "
        "filtered where ordered_at < '2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": date(2026, 1, 2),
            }
        ],
    },
    {
        "name": "subquery from",
        "sql": "select * from (select ordered_at from shop.orders) t where t.ordered_at >= "
        "'2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            }
        ],
    },
    {
        "name": "join subquery",
        "sql": "select * from shop.users u join (select user_id, ordered_at from "
        "shop.orders) o on u.id = o.user_id and o.ordered_at < '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": date(2026, 1, 1),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "id",
                "lower": None,
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "name",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "qualify clause",
        "sql": "select min(ordered_at) over (partition by user_id) as first_ordered_at from "
        "shop.orders qualify first_ordered_at > '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
                "lower": None,
                "upper": None,
            },
        ],
    },
    {
        "name": "having clause",
        "sql": "select min(ordered_at) as first_ordered_at from shop.orders having "
        "first_ordered_at > '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            }
        ],
    },
    {
        "name": "union both filtered",
        "sql": "select ordered_at from shop.orders where ordered_at >= '2026-01-01' union "
        "all select ordered_at from shop.orders where ordered_at >= '2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            }
        ],
    },
    {
        "name": "union one filtered",
        "sql": "select ordered_at from shop.orders where ordered_at >= '2026-01-01' union "
        "all select ordered_at from shop.orders",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": None,
                "upper": None,
            }
        ],
    },
    {
        "name": "union different tables",
        "sql": "select ordered_at from shop.orders where ordered_at >= '2026-01-01' union "
        "all select event_at from shop.events where event_at < '2026-01-02'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "events",
                "column": "event_at",
                "lower": None,
                "upper": date(2026, 1, 2),
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
                "lower": date(2026, 1, 1),
                "upper": None,
            },
        ],
    },
]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [(case["sql"], case["expected"]) for case in test_cases],
    ids=[case["name"] for case in test_cases],
)
def test_analyze_case(sql, expected):
    result = analyze(
        dialects.Redshift, sql, schema, "production", with_timebounds=True
    )
    assert result == expected


def test_current_date_provider():
    sql = "select * from shop.orders where ordered_at >= current_date()"
    result = analyze(
        dialects.Redshift,
        sql,
        schema,
        "production",
        with_timebounds=True,
        current_date_provider=lambda: "2026-01-01",
    )
    assert result == [
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "id",
            "lower": None,
            "upper": None,
        },
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "ordered_at",
            "lower": date(2026, 1, 1),
            "upper": None,
        },
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "user_id",
            "lower": None,
            "upper": None,
        },
    ]


def test_current_datetime_provider():
    sql = "select * from shop.orders where ordered_at >= current_timestamp()"
    result = analyze(
        dialects.Redshift,
        sql,
        schema,
        "production",
        with_timebounds=True,
        current_date_provider=lambda: "2026-01-01",
    )
    assert result == [
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "id",
            "lower": None,
            "upper": None,
        },
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "ordered_at",
            "lower": date(2026, 1, 1),
            "upper": None,
        },
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "user_id",
            "lower": None,
            "upper": None,
        },
    ]


def test_current_timestamp_provider():
    sql = "select * from shop.orders where ordered_at >= current_timestamp()"
    result = analyze(
        dialects.Redshift,
        sql,
        schema,
        "production",
        with_timebounds=True,
        current_date_provider=lambda: "2026-01-01",
    )
    assert result == [
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "id",
            "lower": None,
            "upper": None,
        },
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "ordered_at",
            "lower": date(2026, 1, 1),
            "upper": None,
        },
        {
            "database": "production",
            "schema": "shop",
            "table": "orders",
            "column": "user_id",
            "lower": None,
            "upper": None,
        },
    ]
