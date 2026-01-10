import pytest

from analyzer import analyze


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
    {"name": "not referencing a table", "sql": "select 1", "expected": {}},
    {
        "name": "referencing a table but not columns",
        "sql": "select count(1) from shop.orders",
        "expected": {},
    },
    {
        "name": "simple column reference",
        "sql": "select user_id from shop.orders",
        "expected": {"production.shop.orders": {"user_id"}},
    },
    {
        "name": "qualifying a table with a project",
        "sql": "select user_id from production.shop.orders",
        "expected": {"production.shop.orders": {"user_id"}},
    },
    {
        "name": "qualifying a table with a non-default project",
        "sql": "select id from development.shop.users",
        "expected": {"development.shop.users": {"id"}},
    },
    {
        "name": "referencing a column in a where clause",
        "sql": "select count(1) from shop.orders where ordered_at >= '2026-01-01'",
        "expected": {"production.shop.orders": {"ordered_at"}},
    },
    {
        "name": "referencing a column in a join",
        "sql": "select count(1) from shop.orders join shop.users on orders.user_id = users.id",
        "expected": {
            "production.shop.orders": {"user_id"},
            "production.shop.users": {"id"},
        },
    },
    {
        "name": "referencing a column in an ORDER BY clause",
        "sql": "select user_id from shop.orders order by payment_amount desc",
        "expected": {"production.shop.orders": {"user_id", "payment_amount"}},
    },
    {
        "name": "wildcard pattern",
        "sql": "select * from shop.users",
        "expected": {
            "production.shop.users": set(schema["production"]["shop"]["users"].keys())
        },
    },
    {
        "name": "using a wildcard with COUNT",
        "sql": "select count(*) from shop.users",
        "expected": {},
    },
    {
        "name": "SELECT EXCEPT pattern",
        "sql": "select * except (name) from shop.users",
        "expected": {"production.shop.users": {"id"}},
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
        "expected": {"production.shop.orders": {"payment_method", "payment_amount"}},
    },
    {
        "name": "referencing a field of a struct",
        "sql": "select brand.category from shop.items",
        "expected": {"production.shop.items": {"brand.category"}},
    },
    {
        "name": "referencing fields of a struct with a wildcard",
        "sql": "select brand.* from shop.items",
        "expected": {"production.shop.items": {"brand.*"}},
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
        "expected": {"production.shop.orders": {"items"}},
    },
]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [(case["sql"], case["expected"]) for case in test_cases],
    ids=[case["name"] for case in test_cases],
)
def test_analyze_case(sql, expected):
    result = analyze(sql, schema, "production")
    assert result == expected
