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

Extract table/column references from a single SQL statement. Passing multiple statements raises `ValueError`. Dialects can be passed as classes or names such as `"bigquery"`.

Schema format follows sqlglot conventions, with nested fields represented as nested dicts.
A table referenced without a specific column, such as in `COUNT(*)`, is returned with `column=None`.

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

### analyze with time bounds

Extract time bounds from filters by enabling `with_timebounds`.

```python
from datetime import date

from analytics_query_analyzer import analyze
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

timebounds = analyze(
    dialects.BigQuery,
    sql,
    schema,
    "production",
    with_timebounds=True,
)
print(timebounds)
# [
#   {
#     "database": "production",
#     "schema": "shop",
#     "table": "orders",
#     "column": "id",
#     "lower": None,
#     "upper": None,
#   },
#   {
#     "database": "production",
#     "schema": "shop",
#     "table": "orders",
#     "column": "ordered_at",
#     "lower": date(2025, 1, 1),
#     "upper": date(2026, 1, 1),
#   },
#   {
#     "database": "production",
#     "schema": "shop",
#     "table": "orders",
#     "column": "user_id",
#     "lower": None,
#     "upper": None,
#   },
# ]
```

Bounds are inclusive, conservative `date` values inferred from SQL predicates, not the actual scan range. Time-of-day precision is lost, and timezone-aware literals are converted to UTC. `None` means unbounded or unknown. For example, `ordered_at < DATE '2026-02-01'` yields an upper bound of `date(2026, 2, 1)`.

For BigQuery, `_TABLE_SUFFIX` bounds are strings; `_PARTITIONDATE` and `_PARTITIONTIME` are also supported. Wildcard tables use the union of matching table schemas; conflicting field types and ambiguous references may be unknown. The default current date is evaluated in UTC.

To make `current_date()` deterministic, pass a provider:

```python
timebounds = analyze(
    dialects.BigQuery,
    "select * from shop.orders where ordered_at >= current_date()",
    schema,
    "production",
    with_timebounds=True,
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
- The returned `schema` can be passed directly to `analyze`.

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
