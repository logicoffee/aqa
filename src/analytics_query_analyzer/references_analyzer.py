from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from .column_resolver import resolve_column_path


class ReferencesAnalyzer:
    def __init__(self, schema: dict, default_catalog: str):
        self.schema = schema
        self.default_catalog = default_catalog

    def analyze(self, expression: exp.Expression) -> list[dict[str, str]]:
        references: dict[str, set[str]] = {}

        for scope in traverse_scope(expression):
            for column in scope.columns:
                resolved = resolve_column_path(
                    column,
                    scope,
                    self.default_catalog,
                    self.schema,
                    _extract_column,
                )
                if not resolved:
                    continue
                full_path, column_path = resolved
                table_path = ".".join(full_path.split(".", 3)[:3])
                _add(references, table_path, column_path)

        return _flatten_references(references)

def _add(references: dict[str, set[str]], table: str, column: str):
    if table in references:
        references[table].add(column)
    else:
        references[table] = {column}


def _flatten_references(references: dict[str, set[str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for table_path, columns in references.items():
        database, schema, table = table_path.split(".", 2)
        for column in columns:
            rows.append(
                {
                    "database": database,
                    "schema": schema,
                    "table": table,
                    "column": column,
                }
            )
    rows.sort(key=lambda row: (row["database"], row["schema"], row["table"], row["column"]))
    return rows


def _extract_column(expr: exp.Expression) -> exp.Column | None:
    if isinstance(expr, exp.Column):
        return expr
    if isinstance(expr, exp.Cast):
        return _extract_column(expr.this)
    if isinstance(expr, exp.Paren):
        return _extract_column(expr.this)
    columns = list(expr.find_all(exp.Column))
    if len(columns) == 1:
        return columns[0]
    return None
