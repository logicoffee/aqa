import pytest
from sqlglot import dialects

from analytics_query_analyzer.analyzer import analyze


schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "datetime",
                "user_id": "int64",
                "payment_amount": "int64",
                "payment_method": "string",
                "items": "array<struct<item_id int64, amount int64>>",
            },
            "users": {"id": "int64", "name": "string"},
            "items": {
                "id": "int64",
                "name": "string",
                "brand": {"category": "string", "name": "string"},
            },
        }
    },
    "development": {
        "shop": {
            "users": {"id": "int64", "name": "string"},
        }
    },
}


test_cases = [
    {"name": "not referencing a table", "sql": "select 1", "expected": []},
    {
        "name": "referencing a table but not columns",
        "sql": "select count(1) from shop.orders",
        "expected": [{"database": "production", "schema": "shop", "table": "orders", "column": None}],
    },
    {
        "name": "simple column reference",
        "sql": "select user_id from shop.orders",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
            }
        ],
    },
    {
        "name": "qualifying a table with a project",
        "sql": "select user_id from production.shop.orders",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
            }
        ],
    },
    {
        "name": "qualifying a table with a non-default project",
        "sql": "select id from development.shop.users",
        "expected": [
            {
                "database": "development",
                "schema": "shop",
                "table": "users",
                "column": "id",
            }
        ],
    },
    {
        "name": "referencing a column in a where clause",
        "sql": "select count(1) from shop.orders where ordered_at >= '2026-01-01'",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "ordered_at",
            }
        ],
    },
    {
        "name": "referencing a column in a join",
        "sql": "select count(1) from shop.orders join shop.users on orders.user_id = users.id",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "id",
            },
        ],
    },
    {
        "name": "referencing a column in an ORDER BY clause",
        "sql": "select user_id from shop.orders order by payment_amount desc",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "payment_amount",
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "user_id",
            },
        ],
    },
    {
        "name": "wildcard pattern",
        "sql": "select * from shop.users",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": column,
            }
            for column in schema["production"]["shop"]["users"].keys()
        ],
    },
    {
        "name": "using a wildcard with COUNT",
        "sql": "select count(*) from shop.users",
        "expected": [{"database": "production", "schema": "shop", "table": "users", "column": None}],
    },
    {
        "name": "SELECT EXCEPT pattern",
        "sql": "select * except (name) from shop.users",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "id",
            }
        ],
    },
    {
        "name": "CTE pattern",
        "sql": """
            with amount_by_method as (
                select
                    payment_method,
                    sum(payment_amount) as total_amount
                from
                    shop.orders
                group by
                    1
            )
            select
                *
            from
                amount_by_method
        """,
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "payment_amount",
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "payment_method",
            },
        ],
    },
    {
        "name": "referencing a field of a struct",
        "sql": "select brand.category from shop.items",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "items",
                "column": "brand.category",
            }
        ],
    },
    {
        "name": "referencing fields of a struct with a wildcard",
        "sql": "select brand.* from shop.items",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "items",
                "column": column,
            }
            for column in ("brand.category", "brand.name")
        ],
    },
    {
        "name": "referencing a field in an unnested struct",
        "sql": """
            select
                count(1)
            from
                shop.orders
            where
                exists (select 1 from unnest(items) where amount > 1)
        """,
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "orders",
                "column": "items",
            }
        ],
    },
]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [(case["sql"], case["expected"]) for case in test_cases],
    ids=[case["name"] for case in test_cases],
)
def test_analyze_case(sql, expected):
    result = analyze(dialects.BigQuery, sql, schema, "production")
    assert _sorted_rows(result) == _sorted_rows(expected)


def _sorted_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (row["database"], row["schema"], row["table"], row["column"]),
    )
