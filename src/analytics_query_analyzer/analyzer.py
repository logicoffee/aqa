from sqlglot import dialects, optimizer, parse_one

from .references_analyzer import ReferencesAnalyzer
from .timespan_analyzer import TimespanAnalyzer
from .types import ReferenceRow, TimespanRow


def _resolve_dialect(
    dialect: str | type[dialects.Dialect],
) -> type[dialects.Dialect]:
    if isinstance(dialect, str):
        return dialects.get_or_raise(dialect.lower())
    return dialect


def analyze(
    dialect: str | type[dialects.Dialect],
    sql: str,
    schema: dict,
    default_catalog: str,
    include_timespan: bool = False,
    current_date_provider=None,
):
    dialect = _resolve_dialect(dialect)
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_catalog,
        validate_qualify_columns=False,
    )
    analyzer = ReferencesAnalyzer(schema, default_catalog)
    references = analyzer.analyze(qualified)
    if not include_timespan:
        return references
    return _merge_timespans(
        references,
        TimespanAnalyzer(schema, default_catalog, current_date_provider).analyze(
            qualified
        ),
    )


def _merge_timespans(
    references: list[ReferenceRow],
    timespans: list[TimespanRow],
) -> list[TimespanRow]:
    merged: dict[tuple[str, str, str, str], TimespanRow] = {}
    for row in references:
        key = (row["database"], row["schema"], row["table"], row["column"])
        merged[key] = {**row, "lower": None, "upper": None}
    for row in timespans:
        key = (row["database"], row["schema"], row["table"], row["column"])
        if key in merged:
            merged[key]["lower"] = row.get("lower")
            merged[key]["upper"] = row.get("upper")
        else:
            merged[key] = row
    return [
        merged[key]
        for key in sorted(merged.keys(), key=lambda k: (k[0], k[1], k[2], k[3]))
    ]


__all__ = ["analyze"]
