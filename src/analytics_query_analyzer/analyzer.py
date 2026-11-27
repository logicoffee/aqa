from copy import deepcopy
from typing import Literal, overload

from sqlglot import dialects, exp, optimizer, parse
from sqlglot.optimizer.scope import traverse_scope

from .references_analyzer import ReferencesAnalyzer
from .timebounds_analyzer import TimeboundsAnalyzer
from .types import ReferenceRow, TimeboundsRow


def _resolve_dialect(
    dialect: str | type[dialects.Dialect],
) -> type[dialects.Dialect]:
    if isinstance(dialect, str):
        return type(dialects.Dialect.get_or_raise(dialect.lower()))
    return dialect


@overload
def analyze(
    dialect: str | type[dialects.Dialect],
    sql: str,
    schema: dict,
    default_catalog: str,
    with_timebounds: Literal[False] = False,
    current_date_provider=None,
) -> list[ReferenceRow]: ...


@overload
def analyze(
    dialect: str | type[dialects.Dialect],
    sql: str,
    schema: dict,
    default_catalog: str,
    with_timebounds: Literal[True],
    current_date_provider=None,
) -> list[TimeboundsRow]: ...


def analyze(
    dialect: str | type[dialects.Dialect],
    sql: str,
    schema: dict,
    default_catalog: str,
    with_timebounds: bool = False,
    current_date_provider=None,
) -> list[ReferenceRow] | list[TimeboundsRow]:
    dialect = _resolve_dialect(dialect)
    statements = [
        statement for statement in parse(sql, read=dialect) if statement is not None
    ]
    if len(statements) != 1:
        raise ValueError("Expected a single SQL statement")
    expression = statements[0]

    if dialect is dialects.BigQuery:
        schema = _bigquery_schema(schema, expression, default_catalog)

    # sqlglot rejects empty schema branches; an empty branch supplies no types.
    optimizer_schema = {
        catalog: {
            dataset: {table: fields for table, fields in tables.items() if fields}
            for dataset, tables in datasets.items()
            if any(tables.values())
        }
        for catalog, datasets in schema.items()
        if any(any(tables.values()) for tables in datasets.values())
    }
    if dialect is dialects.BigQuery:
        for datasets in optimizer_schema.values():
            for tables in datasets.values():
                for table, fields in tables.items():
                    tables[table] = {
                        name: _bigquery_struct_type(value)
                        for name, value in fields.items()
                    }
    qualified = optimizer.qualify.qualify(
        expression,
        dialect=dialect,
        schema=optimizer_schema,
        catalog=default_catalog,
        validate_qualify_columns=False,
        allow_partial_qualification=True,
    )
    if dialect is dialects.BigQuery:
        _qualify_bigquery_pseudocolumns(qualified)
    analyzer = ReferencesAnalyzer(schema, default_catalog)
    references: list[ReferenceRow] = analyzer.analyze(qualified)
    if not with_timebounds:
        return references
    return _merge_timebounds(
        references,
        TimeboundsAnalyzer(
            schema, default_catalog, current_date_provider, dialect
        ).analyze(qualified),
    )


def _bigquery_struct_type(value):
    if not isinstance(value, dict):
        return value
    fields = [
        f"{exp.to_identifier(name, quoted=True).sql(dialect='bigquery')} {_bigquery_struct_type(field_type)}"
        for name, field_type in value.items()
    ]
    return f"STRUCT<{', '.join(fields)}>"


def _qualify_bigquery_pseudocolumns(expression: exp.Expression) -> None:
    for scope in traverse_scope(expression):
        sources = scope.selected_sources
        if len(sources) != 1:
            continue
        alias, (_, source) = next(iter(sources.items()))
        if not isinstance(source, exp.Table):
            continue
        if source.name.endswith("*") and not scope.can_be_correlated:
            for column in scope.columns:
                if not column.table and not isinstance(column.this, exp.Star):
                    column.set("table", exp.to_identifier(alias))
        for pseudo in list(scope.expression.find_all(exp.Pseudocolumn)):
            if pseudo.find_ancestor(
                exp.Select
            ) is scope.expression and pseudo.name.lower() in {
                "_partitiondate",
                "_partitiontime",
                "_table_suffix",
            }:
                pseudo.replace(exp.column(pseudo.name.lower(), table=alias))


def _bigquery_schema(
    schema: dict, expression: exp.Expression, default_catalog: str
) -> dict:
    """Provide schemas for referenced wildcard tables and pseudo-columns."""
    schema = deepcopy(schema)
    pseudo_types = {
        "_partitiondate": "date",
        "_partitiontime": "timestamp",
        "_table_suffix": "string",
    }
    used_pseudos = {
        column.name.lower() for column in expression.find_all(exp.Column)
    } & pseudo_types.keys()
    for table in expression.find_all(exp.Table):
        project = table.catalog or default_catalog
        datasets = schema.get(project, {})
        dataset = table.db
        if not dataset:
            matches = [
                name
                for name, tables in datasets.items()
                if table.name in tables
                or (
                    table.name.endswith("*")
                    and any(t.startswith(table.name[:-1]) for t in tables)
                )
            ]
            if len(matches) != 1:
                continue
            dataset = matches[0]
        tables = datasets.get(dataset, {})
        if table.name.endswith("*") and table.name not in tables:
            matches = sorted(
                name for name in tables if name.startswith(table.name[:-1])
            )
            if matches:
                merged_fields = {}
                for match in matches:
                    merged_fields = _merge_wildcard_fields(merged_fields, tables[match])
                tables[table.name] = merged_fields
        fields = tables.get(table.name)
        if isinstance(fields, dict):
            for name in used_pseudos:
                if name != "_table_suffix" or table.name.endswith("*"):
                    fields.setdefault(name, pseudo_types[name])
    return schema


def _merge_wildcard_fields(left: dict, right: dict) -> dict:
    """Keep every possible field; conflicting types have no reliable type."""
    result = deepcopy(left)
    for name, right_type in right.items():
        if name not in result:
            result[name] = deepcopy(right_type)
        elif isinstance(result[name], dict) and isinstance(right_type, dict):
            result[name] = _merge_wildcard_fields(result[name], right_type)
        elif result[name] != right_type:
            result[name] = "unknown"
    return result


def _merge_timebounds(
    references: list[ReferenceRow],
    timebounds: list[TimeboundsRow],
) -> list[TimeboundsRow]:
    merged: dict[tuple[str, str, str, str | None], TimeboundsRow] = {}
    for row in references:
        key = (row["database"], row["schema"], row["table"], row["column"])
        merged[key] = {**row, "lower": None, "upper": None}
    for row in timebounds:
        key = (row["database"], row["schema"], row["table"], row["column"])
        if key in merged:
            merged[key]["lower"] = row.get("lower")
            merged[key]["upper"] = row.get("upper")
        else:
            merged[key] = row
    return [
        merged[key]
        for key in sorted(merged.keys(), key=lambda k: (k[0], k[1], k[2], k[3] or ""))
    ]


__all__ = ["analyze"]
