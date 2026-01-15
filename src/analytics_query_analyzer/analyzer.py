from sqlglot import dialects, optimizer, parse_one

from .references_analyzer import ReferencesAnalyzer
from .timespan_analyzer import TimespanAnalyzer


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
    default_project: str,
):
    dialect = _resolve_dialect(dialect)
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_project,
        validate_qualify_columns=False,
    )
    analyzer = ReferencesAnalyzer(schema, default_project)
    return analyzer.analyze(qualified)


def analyze_timespan(
    dialect: str | type[dialects.Dialect],
    sql: str,
    schema: dict,
    default_project: str,
    current_date_provider=None,
) -> dict:
    dialect = _resolve_dialect(dialect)
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_project,
        validate_qualify_columns=False,
    )
    analyzer = TimespanAnalyzer(schema, default_project, current_date_provider)
    return analyzer.analyze(qualified)


__all__ = ["analyze", "analyze_timespan"]
