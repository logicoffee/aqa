from sqlglot import exp
from sqlglot.optimizer.scope import Scope


def resolve_column_path(
    column: exp.Column,
    scope,
    default_catalog: str,
    schema: dict,
    column_extractor,
) -> tuple[str, str] | None:
    table_alias = column.table
    source = scope.sources.get(table_alias)
    if isinstance(source, Scope):
        select_expression = None
        if source.expression:
            named = source.expression.named_selects
            if column.name in named:
                select_expression = source.expression.selects[named.index(column.name)]
        if not select_expression:
            return None
        if isinstance(select_expression, exp.Alias):
            select_expression = select_expression.this
        nested_column = column_extractor(select_expression)
        if not nested_column:
            return None
        return resolve_column_path(
            nested_column, source, default_catalog, schema, column_extractor
        )
    if not isinstance(source, exp.Table):
        return None

    project = source.catalog or default_catalog
    dataset = source.db
    table = source.name
    if not dataset and project in schema:
        matches = [
            dataset_name
            for dataset_name, tables in schema[project].items()
            if table in tables
        ]
        if len(matches) == 1:
            dataset = matches[0]
        else:
            return None
    if not dataset:
        return None

    fields = []
    parent = column.parent
    while isinstance(parent, exp.Dot):
        fields.append(parent.expression.name)
        parent = parent.parent

    if column.parts[0].name == column.table:
        column_full_path = ".".join(p.name for p in column.parts[1:])
    else:
        column_full_path = ".".join(p.name for p in column.parts)
    if fields:
        column_full_path = column_full_path + "." + ".".join(fields)

    return f"{project}.{dataset}.{table}.{column_full_path}", column_full_path
