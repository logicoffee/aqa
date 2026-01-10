from sqlglot import dialects, exp, optimizer, parse_one
from sqlglot.optimizer.scope import traverse_scope


def analyze(sql: str, schema: dict, default_project: str):
    dialect = dialects.BigQuery  # currently only support BigQuery
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_project,
        validate_qualify_columns=False,
    )

    references = {}

    for scope in traverse_scope(qualified):
        for column in scope.columns:
            table_alias = column.table
            source = scope.sources.get(table_alias)

            if isinstance(source, exp.Table):
                project = source.catalog
                dataset = source.db
                table = source.name

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
                _add(references, f"{project}.{dataset}.{table}", column_full_path)

    return references


def _add(references: dict[str, set[str]], table: str, column: str):
    if table in references:
        references[table].add(column)
    else:
        references[table] = {column}
