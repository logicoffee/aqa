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
        "name": "upper bound (<=)",
        "sql": "select * from shop.orders where ordered_at <= '2026-01-01'",
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
        "name": "trunc column",
        "sql": "select * from shop.orders where date_trunc(ordered_at, month) >= '2026-02-10'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-02-01",
                "upper": None,
            }
        },
    },
    {
        "name": "date function string",
        "sql": "select * from shop.orders where ordered_at >= date('2026-01-01')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "date from parts",
        "sql": "select * from shop.orders where ordered_at >= date(2026, 1, 1)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "date literal",
        "sql": "select * from shop.orders where ordered_at >= date '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "datetime function string",
        "sql": "select * from shop.orders where ordered_at >= datetime('2026-01-01 09:00:00')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "datetime from parts",
        "sql": "select * from shop.orders where ordered_at >= datetime(2026, 1, 1, 9, 0, 0)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "datetime literal",
        "sql": "select * from shop.orders where ordered_at >= datetime '2026-01-01 09:00:00'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "timestamp function string",
        "sql": "select * from shop.orders where ordered_at >= timestamp('2026-01-01 09:00:00')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "timestamp literal",
        "sql": "select * from shop.orders where ordered_at >= timestamp '2026-01-01 09:00:00'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "timestamp from date",
        "sql": "select * from shop.orders where ordered_at >= timestamp(date '2026-01-01')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "date sub day",
        "sql": "select * from shop.orders where ordered_at > date_sub(date('2026-01-04'), interval 3 day)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "date add day",
        "sql": "select * from shop.orders where ordered_at >= date_add(date('2026-01-04'), interval 2 day)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-06",
                "upper": None,
            }
        },
    },
    {
        "name": "date add month",
        "sql": "select * from shop.orders where ordered_at >= date_add(date('2026-01-31'), interval 1 month)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-02-28",
                "upper": None,
            }
        },
    },
    {
        "name": "trunc literal",
        "sql": "select * from shop.orders where ordered_at >= date_trunc('2026-02-10', month)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-02-01",
                "upper": None,
            }
        },
    },
    {
        "name": "cast date",
        "sql": "select * from shop.orders where ordered_at >= cast('2026-01-01' as date)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "cast datetime",
        "sql": "select * from shop.orders where ordered_at >= cast('2026-01-01 09:00:00' as datetime)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "cast timestamp",
        "sql": "select * from shop.orders where ordered_at >= cast('2026-01-01 09:00:00' as timestamp)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "timestamp seconds",
        "sql": "select * from shop.orders where ordered_at >= timestamp_seconds(1767229200)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "timestamp millis",
        "sql": "select * from shop.orders where ordered_at >= timestamp_millis(1767229200000)",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "parse date",
        "sql": "select * from shop.orders where ordered_at >= parse_date('%Y-%m-%d', '2026-01-01')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "parse datetime",
        "sql": "select * from shop.orders where ordered_at >= parse_datetime('%Y-%m-%d %H:%M:%S', '2026-01-01 09:00:00')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "parse timestamp",
        "sql": "select * from shop.orders where ordered_at >= parse_timestamp('%Y-%m-%d %H:%M:%S', '2026-01-01 09:00:00')",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-01",
                "upper": None,
            }
        },
    },
    {
        "name": "differently formatted literals",
        "sql": "select * from shop.orders where ordered_at >= '2026-01-01' and ordered_at > '2026-01-02 09:00:00'",
        "expected": {
            "production.shop.orders.ordered_at": {
                "lower": "2026-01-02",
                "upper": None,
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
        "name": "negation",
        "sql": "select * from shop.orders where not ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": "2026-01-01"}
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
        "name": "lower > upper",
        "sql": "select * from shop.orders where ordered_at > '2026-01-02' and ordered_at < '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": None}
        },
    },
    {
        "name": "lower > upper between",
        "sql": "select * from shop.orders where ordered_at between '2026-01-02' and '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": None, "upper": None}
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
        "name": "cte",
        "sql": "with base as (select ordered_at from shop.orders) select * from base where ordered_at > '2026-01-01'",
        "expected": {
            "production.shop.orders.ordered_at": {"lower": "2026-01-01", "upper": None}
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
