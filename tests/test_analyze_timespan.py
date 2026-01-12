import pytest

from analytics_query_analyzer.analyzer import analyze_timespan

schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "datetime",
                "user_id": "int64",
            },
            "events": {
                "id": "int64",
                "event_at": "datetime",
                "user_id": "int64",
            },
            "users": {"id": "int64", "name": "string"},
        }
    },
}

test_cases = [
    {
        "name": "without condition",
        "sql": "select ordered_at from shop.orders",
        "expected": {},
    },
    {
        "name": "lower bound (>)",
        "sql": "select * from shop.orders where ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": "2026-01-01", "upper": None}
        },
    },
    {
        "name": "lower bound (>=)",
        "sql": "select * from shop.orders where ordered_at >= '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": "2026-01-01", "upper": None}
        },
    },
    {
        "name": "upper bound (<)",
        "sql": "select * from shop.orders where ordered_at < '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": "2026-01-01"}
        },
    },
    {
        "name": "equality",
        "sql": "select * from shop.orders where ordered_at = '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-01",
            }
        },
    },
    {
        "name": "in clause",
        "sql": "select * from shop.orders where ordered_at in ('2026-01-01')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-01",
            }
        },
    },
    {
        "name": "upper bound (<=)",
        "sql": "select * from shop.orders where ordered_at <= '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": "2026-01-01"}
        },
    },
    {
        "name": "lower and upper bound",
        "sql": "select * from shop.orders where ordered_at >= '2026-01-01' and ordered_at < '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-02",
            }
        },
    },
    {
        "name": "between",
        "sql": "select * from shop.orders where ordered_at between '2026-01-01' and '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-02",
            }
        },
    },
    {
        "name": "between mixed literal",
        "sql": "select * from shop.orders where ordered_at between '2026-01-01' and current_date",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "multiple conditions (and)",
        "sql": "select * from orders where ordered_at > '2026-01-01' and ordered_at > '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": "2026-01-02", "upper": None}
        },
    },
    {
        "name": "multiple conditions (or)",
        "sql": "select * from shop.orders where ordered_at > '2026-01-01' or ordered_at > '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": "2026-01-01", "upper": None}
        },
    },
    {
        "name": "function wrapped column",
        "sql": "select * from shop.orders where date(ordered_at) >= '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "function wrapped mixed conditions",
        "sql": "select * from shop.orders where date(ordered_at) >= '2026-01-01' and ordered_at < '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-02",
            }
        },
    },
    {
        "name": "mixed literal and non-literal",
        "sql": "select * from shop.orders where ordered_at >= '2026-01-01' and ordered_at < current_date",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "negation",
        "sql": "select * from shop.orders where not ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": "2026-01-01"}
        },
    },
    {
        "name": "not equal",
        "sql": "select * from shop.orders where ordered_at != '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": None}
        },
    },
    {
        "name": "not equal (alt)",
        "sql": "select * from shop.orders where ordered_at <> '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": None}
        },
    },
    {
        "name": "join condition",
        "sql": "select * from shop.users join shop.orders on users.id = orders.user_id and orders.ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": "2026-01-01", "upper": None}
        },
    },
    {
        "name": "multiple tables",
        "sql": "select * from shop.orders join shop.events on orders.user_id = events.user_id where orders.ordered_at >= '2026-01-01' and events.event_at > '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            },
            "production.shop.events.event_at": {
                "lower": "2026-01-02",
                "upper": None,
            },
        },
    },
    {
        "name": "lower > upper",
        "sql": "select * from shop.orders where ordered_at > '2026-01-02' and ordered_at < '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": None}
        },
    },
    {
        "name": "in mixed literal",
        "sql": "select * from shop.orders where ordered_at in ('2026-01-01', current_date)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-01",
            }
        },
    },
    {
        "name": "non-literal",
        "sql": "select * from shop.orders where ordered_at > date_sub(current_date, interval 1 month)",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": None}
        },
    },
    {
        "name": "cte",
        "sql": "with base as (select ordered_at from shop.orders) select * from base where ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": "2026-01-01", "upper": None}
        },
    },
    {
        "name": "multi cte",
        "sql": "with base as (select ordered_at from shop.orders), filtered as (select ordered_at from base where ordered_at >= '2026-01-01') select * from filtered where ordered_at < '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-02",
            }
        },
    },
    {
        "name": "cte inner and outer",
        "sql": "with base as (select ordered_at from shop.orders where ordered_at >= '2026-01-01') select * from base where ordered_at < '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": "2026-01-02",
            }
        },
    },
    {
        "name": "subquery from",
        "sql": "select * from (select ordered_at from shop.orders) t where t.ordered_at >= '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "qualify clause",
        "sql": "select min(ordered_at) over (partition by user_id) as first_ordered_at from shop.orders qualify first_ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "join subquery",
        "sql": "select * from shop.users u join (select user_id, ordered_at from shop.orders) o on u.id = o.user_id and o.ordered_at < '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": None,
                "upper": "2026-01-01",
            }
        },
    },
    {
        "name": "having clause",
        "sql": "select min(ordered_at) as first_ordered_at from shop.orders having first_ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "union both filtered",
        "sql": "select ordered_at from shop.orders where ordered_at >= '2026-01-01' union all select ordered_at from shop.orders where ordered_at >= '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "union one filtered",
        "sql": "select ordered_at from shop.orders where ordered_at >= '2026-01-01' union all select ordered_at from shop.orders",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "union different tables",
        "sql": "select ordered_at from shop.orders where ordered_at >= '2026-01-01' union all select event_at from shop.events where event_at < '2026-01-02'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            },
            "production.shop.events.event_at": {
                "lower": None,
                "upper": "2026-01-02",
            },
        },
    },
]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [(case["sql"], case["expected"]) for case in test_cases],
    ids=[case["name"] for case in test_cases],
)
def test_analyze_case(sql, expected):
    result = analyze_timespan(sql, schema, "production")
    assert result == expected
