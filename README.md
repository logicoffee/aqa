# analytics-query-analyzer

Analytics Query Analyzer

## Install

```bash
pip install analytics-query-analyzer
```

## Usage

```python
from analytics_query_analyzer import analyze

schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "datetime",
                "user_id": "int64",
                "payment_amount": "int64",
                "payment_method": "string",
            }
        }
    }
}

references = analyze("select user_id from shop.orders", schema, "production")
print(references)  # {'production.shop.orders': {'user_id'}}
```

### Timespan analysis

```python
from analytics_query_analyzer import analyze_timespan

sql = """
select
    sum(payment_amount)
from
    shop.orders
where
    ordered_at >= "2025-01-01"
    and ordered_at < "2026-01-01"
"""

schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "datetime",
                "user_id": "int64",
                "payment_amount": "int64",
                "payment_method": "string",
            }
        }
    }
}

timespans = analyze_timespan(sql, schema, "production")
print(timespans)
# {
#   "production.shop.orders.ordered_at": {
#     "lower": "2025-01-01",
#     "upper": "2026-01-01"
#   }
# }
```

If you want to make `current_date()` deterministic in tests, pass a provider:

```python
timespans = analyze_timespan(
    "select * from shop.orders where ordered_at >= current_date()",
    schema,
    "production",
    current_date_provider=lambda: "2026-01-01",
)
```
