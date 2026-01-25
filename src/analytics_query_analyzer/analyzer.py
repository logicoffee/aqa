from typing import Literal, overload

from sqlglot import dialects, optimizer, parse_one

from .references_analyzer import ReferencesAnalyzer
from .timebounds_analyzer import TimeboundsAnalyzer
from .types import ReferenceRow, TimeboundsRow


def _resolve_dialect(
    dialect: str | type[dialects.Dialect],
) -> type[dialects.Dialect]:
    if isinstance(dialect, str):
        return dialects.get_or_raise(dialect.lower())
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
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_catalog,
        validate_qualify_columns=False,
    )
    analyzer = ReferencesAnalyzer(schema, default_catalog)
    references: list[ReferenceRow] = analyzer.analyze(qualified)
    if not with_timebounds:
        return references
    return _merge_timebounds(
        references,
        TimeboundsAnalyzer(schema, default_catalog, current_date_provider).analyze(
            qualified
        ),
    )


def _merge_timebounds(
    references: list[ReferenceRow],
    timebounds: list[TimeboundsRow],
) -> list[TimeboundsRow]:
    merged: dict[tuple[str, str, str, str], TimeboundsRow] = {}
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
        for key in sorted(merged.keys(), key=lambda k: (k[0], k[1], k[2], k[3]))
    ]


__all__ = ["analyze"]
