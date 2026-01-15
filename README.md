# analytics-query-analyzer

Analyze analytics SQL to extract referenced tables/columns and time bounds.

## Install

Base install:

```bash
pip install analytics-query-analyzer
```

BigQuery extras (only needed for `build_schema`):

```bash
pip install analytics-query-analyzer[bigquery]
```

## Support

BigQuery is currently supported and tested.

## Schema format

Schemas follow sqlglot conventions, with nested fields represented as nested dicts.

## Usage

### analyze

Extract table/column references from a query.

```python
from analytics_query_analyzer import analyze
from sqlglot import dialects

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

references = analyze(dialects.BigQuery, sql, schema, "production")
print(references)
# {"production.shop.orders": {"id", "user_id", "payment.amount"}}
```

### analyze_timespan

Extract time bounds from filters.

```python
from analytics_query_analyzer import analyze_timespan
from sqlglot import dialects

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

timespans = analyze_timespan(dialects.BigQuery, sql, schema, "production")
print(timespans)
# {
#   "production.shop.orders.ordered_at": {
#     "lower": "2025-01-01",
#     "upper": "2026-01-01"
#   }
# }
```

To make `current_date()` deterministic, pass a provider:

```python
timespans = analyze_timespan(
    dialects.BigQuery,
    "select * from shop.orders where ordered_at >= current_date()",
    schema,
    "production",
    current_date_provider=lambda: "2026-01-01",
)
```

### build_schema

Fetch a schema dictionary from BigQuery.

```python
from analytics_query_analyzer import build_schema
from sqlglot import dialects

schema = build_schema(dialects.BigQuery, "my_project", "my_schema", "my_table")
print(schema)
```

Authentication uses Application Default Credentials (ADC).
Only BigQuery is supported for `build_schema`.
When `table` is omitted, it scans all tables in the dataset.
When both `dataset` and `table` are omitted, it scans all datasets in the project.
The returned `schema` can be passed directly to `analyze` and `analyze_timespan`.
