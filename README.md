# analytics-query-analyzer

Analyze analytics SQL to extract referenced tables/columns and time bounds.

## Support

BigQuery and Redshift are currently supported.

## Install

Base install:

```bash
pip install analytics-query-analyzer
```

BigQuery extras (only needed for `build_schema`):

```bash
pip install analytics-query-analyzer[bigquery]
```

Redshift extras (only needed for `build_schema`):

```bash
pip install analytics-query-analyzer[redshift]
```

## Usage

### analyze

Extract table/column references from a query.

Schema format follows sqlglot conventions, with nested fields represented as nested dicts.

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
# [
#   {
#     "database": "production",
#     "schema": "shop",
#     "table": "orders",
#     "column": "id",
#   },
#   {
#     "database": "production",
#     "schema": "shop",
#     "table": "orders",
#     "column": "payment.amount",
#   },
#   {
#     "database": "production",
#     "schema": "shop",
#     "table": "orders",
#     "column": "user_id",
#   },
# ]
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
# [
#   {
#     "database": "production",
#     "schema": "shop",
#     "table": "orders",
#     "column": "ordered_at",
#     "lower": "2025-01-01",
#     "upper": "2026-01-01",
#   }
# ]
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

Fetch a schema dictionary from BigQuery or Redshift.

```python
from analytics_query_analyzer import build_schema
from sqlglot import dialects

schema = build_schema(dialects.BigQuery, "my_project", "my_schema", "my_table")
print(schema)
```

- Authentication uses Application Default Credentials (ADC).
- When `table` is omitted, it scans all tables in the dataset.
- When both `dataset` and `table` are omitted, it scans all datasets in the project.
- The returned `schema` can be passed directly to `analyze` and `analyze_timespan`.

Fetching from Redshift is also supported:

```python
from analytics_query_analyzer import build_schema
from sqlglot import dialects

schema = build_schema(dialects.Redshift, "my_database", "public", "orders")
print(schema)
```

Redshift authentication supports two modes:

- Set `REDSHIFT_HOST`, `REDSHIFT_USER`, and `REDSHIFT_PASSWORD` (optional `REDSHIFT_PORT`).
- Set `REDSHIFT_CLUSTER_IDENTIFIER`, `REDSHIFT_REGION`, and `REDSHIFT_DB_USER` to use IAM (you can also set `REDSHIFT_HOST`/`REDSHIFT_PORT`).
- Use `AWS_PROFILE` if you want to select a non-default AWS profile.
