# analytics-query-analyzer

Extract table/column references and time bounds from analytics SQL.

## Install

```bash
pip install analytics-query-analyzer
```

## Support

BigQuery is currently supported and tested.
Schema format follows sqlglot's conventions (nested fields are expressed as nested dicts).

## Usage

### analyze

Extract table/column references from a query.

```python
from analytics_query_analyzer import analyze

schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "datetime",
                "user_id": "int64",
                "payment": {
                    "amount": "int64",
                    "method": "string",
                },
            },
        },
    },
}

sql = """
select
    id,
    user_id,
    payment.amount
from
    shop.orders
"""

references = analyze(sql, schema, "production")
print(references)
# {"production.shop.orders": {"id", "user_id", "payment.amount"}}
```

### analyze_timespan

Extract time bounds from filters.

```python
from analytics_query_analyzer import analyze_timespan

schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "datetime",
                "user_id": "int64",
            },
        },
    },
}

sql = """
select
    *
from
    shop.orders
where
    ordered_at >= "2025-01-01"
    and ordered_at < "2026-01-01"
"""

timespans = analyze_timespan(sql, schema, "production")
print(timespans)
# {
#   "production.shop.orders.ordered_at": {
#     "lower": "2025-01-01",
#     "upper": "2026-01-01"
#   }
# }
```

To make `current_date()` deterministic in tests, pass a provider:

```python
timespans = analyze_timespan(
    "select * from shop.orders where ordered_at >= current_date()",
    schema,
    "production",
    current_date_provider=lambda: "2026-01-01",
)
```
