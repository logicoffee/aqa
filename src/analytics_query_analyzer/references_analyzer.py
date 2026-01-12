from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from .column_resolver import resolve_column_path


class ReferencesAnalyzer:
    def __init__(self, schema: dict, default_project: str):
        self.schema = schema
        self.default_project = default_project

    def analyze(self, expression: exp.Expression) -> dict:
        references: dict[str, set[str]] = {}

        for scope in traverse_scope(expression):
            for column in scope.columns:
                resolved = resolve_column_path(
                    column,
                    scope,
                    self.default_project,
                    self.schema,
                    _extract_column,
                )
                if not resolved:
                    continue
                full_path, column_path = resolved
                table_path = ".".join(full_path.split(".", 3)[:3])
                _add(references, table_path, column_path)

        return references

def _add(references: dict[str, set[str]], table: str, column: str):
    if table in references:
        references[table].add(column)
    else:
        references[table] = {column}


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
