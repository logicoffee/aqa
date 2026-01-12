from sqlglot import dialects, optimizer, parse_one

from .references_analyzer import ReferencesAnalyzer
from .timespan_analyzer import TimespanAnalyzer


def analyze(sql: str, schema: dict, default_project: str):
    dialect = dialects.BigQuery  # currently only support BigQuery
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_project,
        validate_qualify_columns=False,
    )
    analyzer = ReferencesAnalyzer(schema, default_project)
    return analyzer.analyze(qualified)


def analyze_timespan(sql: str, schema: dict, default_project: str) -> dict:
    dialect = dialects.BigQuery  # currently only support BigQuery
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_project,
        validate_qualify_columns=False,
    )
    analyzer = TimespanAnalyzer(schema, default_project)
    return analyzer.analyze(qualified)


__all__ = ["analyze", "analyze_timespan"]
