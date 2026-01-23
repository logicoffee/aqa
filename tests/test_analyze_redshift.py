import pytest
from sqlglot import dialects

from analytics_query_analyzer.analyzer import analyze


schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "timestamp",
                "user_id": "int64",
                "payment_amount": "int64",
                "payment_method": "string",
                "items": "super",
            },
            "users": {"id": "int64", "name": "varchar"},
            "items": {
                "id": "int64",
                "name": "varchar",
                "brand": "super",
            },
        }
    },
    "development": {
        "shop": {
            "users": {"id": "int64", "name": "varchar"},
        }
    },
}


test_cases = [
    {"name": "not referencing a table", "sql": "select 1", "expected": []},
    {
        "name": "referencing a table but not columns",
        "sql": "select count(1) from shop.orders",
        "expected": [],
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
        "name": "where clause reference",
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
        "name": "join reference",
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
        "expected": [],
    },
    {
        "name": "selecting multiple columns",
        "sql": "select id, name from shop.users",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "id",
            },
            {
                "database": "production",
                "schema": "shop",
                "table": "users",
                "column": "name",
            },
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
        "name": "referencing a field of a super column",
        "sql": "select brand['category'] from shop.items",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "items",
                "column": "brand",
            }
        ],
    },
    {
        "name": "referencing multiple fields of a super column",
        "sql": "select brand['category'], brand['name'] from shop.items",
        "expected": [
            {
                "database": "production",
                "schema": "shop",
                "table": "items",
                "column": "brand",
            }
        ],
    },
    {
        "name": "referencing a field in a super column filter",
        "sql": """
            select
                count(1)
            from
                shop.orders
            where
                json_extract_path_text(items, 'amount') is not null
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
    result = analyze(dialects.Redshift, sql, schema, "production")
    assert _sorted_rows(result) == _sorted_rows(expected)


def _sorted_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (row["database"], row["schema"], row["table"], row["column"]),
    )
