from sqlglot import dialects, exp, optimizer, parse_one
from sqlglot.optimizer.scope import Scope, traverse_scope


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


def analyze_timespan(sql: str, schema: dict, default_project: str) -> dict:
    dialect = dialects.BigQuery  # currently only support BigQuery
    expression = parse_one(sql, read=dialect)

    qualified = optimizer.qualify.qualify(
        expression,
        schema=schema,
        catalog=default_project,
        validate_qualify_columns=False,
    )

    def extract_column(expr: exp.Expression) -> exp.Column | None:
        if isinstance(expr, exp.Column):
            return expr
        if isinstance(expr, exp.Cast):
            return extract_column(expr.this)
        if isinstance(expr, exp.Paren):
            return extract_column(expr.this)
        if expr.find(exp.Window):
            return None
        columns = list(expr.find_all(exp.Column))
        if len(columns) == 1:
            return columns[0]
        return None

    def extract_window_column(expr: exp.Expression) -> exp.Column | None:
        if not isinstance(expr, exp.Window):
            return None
        if expr.this is None:
            return None
        columns = list(expr.this.find_all(exp.Column))
        if len(columns) == 1:
            return columns[0]
        return None

    def extract_literal(expr: exp.Expression) -> str | None:
        if isinstance(expr, exp.Literal):
            return expr.this
        if isinstance(expr, exp.Cast):
            return extract_literal(expr.this)
        if isinstance(expr, exp.Paren):
            return extract_literal(expr.this)
        if isinstance(expr, (exp.Date, exp.Timestamp, exp.Time)):
            return extract_literal(expr.this)
        return None

    def resolve_column_path(column: exp.Column, scope) -> tuple[str, str] | None:
        table_alias = column.table
        source = scope.sources.get(table_alias)
        if isinstance(source, Scope):
            select_expression = None
            if source.expression:
                named = source.expression.named_selects
                if column.name in named:
                    select_expression = source.expression.selects[
                        named.index(column.name)
                    ]
            if not select_expression:
                return None
            if isinstance(select_expression, exp.Alias):
                select_expression = select_expression.this
            nested_column = extract_column(select_expression)
            if not nested_column:
                return None
            return resolve_column_path(nested_column, source)
        if not isinstance(source, exp.Table):
            return None

        project = source.catalog or default_project
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

    def is_time_column(
        project: str, dataset: str, table: str, column_name: str
    ) -> bool:
        column_root = column_name.split(".", 1)[0]
        try:
            column_type = schema[project][dataset][table][column_root]
        except KeyError:
            return False
        return str(column_type).lower() in {"datetime", "date", "timestamp"}

    def merge_bounds_and(left: dict, right: dict) -> dict:
        merged: dict[str, dict[str, str | None]] = {}
        for key in set(left) | set(right):
            if key in left and key in right:
                lower_left = left[key]["lower"]
                lower_right = right[key]["lower"]
                if lower_left is None:
                    lower = lower_right
                elif lower_right is None:
                    lower = lower_left
                else:
                    lower = max(lower_left, lower_right)

                upper_left = left[key]["upper"]
                upper_right = right[key]["upper"]
                if upper_left is None:
                    upper = upper_right
                elif upper_right is None:
                    upper = upper_left
                else:
                    upper = min(upper_left, upper_right)

                merged[key] = {"lower": lower, "upper": upper}
            else:
                merged[key] = left.get(key, right.get(key))
        return merged

    def merge_bounds_or(left: dict, right: dict) -> dict:
        merged: dict[str, dict[str, str | None]] = {}
        for key in set(left) & set(right):
            lower_left = left[key]["lower"]
            lower_right = right[key]["lower"]
            if lower_left is None or lower_right is None:
                lower = None
            else:
                lower = min(lower_left, lower_right)

            upper_left = left[key]["upper"]
            upper_right = right[key]["upper"]
            if upper_left is None or upper_right is None:
                upper = None
            else:
                upper = max(upper_left, upper_right)

            merged[key] = {"lower": lower, "upper": upper}
        return merged

    def bounds_for_comparison(comparison: exp.Expression, scope) -> dict:
        if isinstance(comparison, exp.Between):
            column = extract_column(comparison.this)
            low = extract_literal(comparison.args.get("low"))
            high = extract_literal(comparison.args.get("high"))
            if not column:
                return {}
            resolved = resolve_column_path(column, scope)
            if not resolved:
                return {}
            full_path, column_path = resolved
            project, dataset, table, _ = full_path.split(".", 3)
            if not is_time_column(project, dataset, table, column_path):
                return {}
            if low is None and high is None:
                return {full_path: {"lower": None, "upper": None}}
            return {full_path: {"lower": low, "upper": high}}

        if isinstance(comparison, exp.In):
            column = extract_column(comparison.this)
            if not column:
                return {}
            resolved = resolve_column_path(column, scope)
            if not resolved:
                return {}
            full_path, column_path = resolved
            project, dataset, table, _ = full_path.split(".", 3)
            if not is_time_column(project, dataset, table, column_path):
                return {}
            literals = [extract_literal(value) for value in comparison.expressions]
            literal_values = [value for value in literals if value is not None]
            if not literal_values:
                return {full_path: {"lower": None, "upper": None}}
            if len(literal_values) == 1:
                return {
                    full_path: {"lower": literal_values[0], "upper": literal_values[0]}
                }
            return {
                full_path: {
                    "lower": min(literal_values),
                    "upper": max(literal_values),
                }
            }

        left = comparison.left
        right = comparison.right
        left_column = extract_column(left)
        right_column = extract_column(right)
        column_side = None
        column = None
        if left_column:
            column = left_column
            column_side = "left"
        elif right_column:
            column = right_column
            column_side = "right"
        else:
            left_window_column = extract_window_column(left)
            right_window_column = extract_window_column(right)
            if left_window_column:
                column = left_window_column
                column_side = "left"
            elif right_window_column:
                column = right_window_column
                column_side = "right"
        literal = (
            extract_literal(right) if column_side == "left" else extract_literal(left)
        )
        if not column:
            return {}

        resolved = resolve_column_path(column, scope)
        if not resolved:
            return {}
        full_path, column_path = resolved
        project, dataset, table, _ = full_path.split(".", 3)
        if not is_time_column(project, dataset, table, column_path):
            return {}
        if literal is None:
            return {full_path: {"lower": None, "upper": None}}

        if isinstance(comparison, exp.NEQ):
            return {full_path: {"lower": None, "upper": None}}

        if isinstance(comparison, exp.EQ):
            return {full_path: {"lower": literal, "upper": literal}}

        if isinstance(comparison, (exp.GT, exp.GTE)):
            bound = "lower" if column_side == "left" else "upper"
        else:
            bound = "upper" if column_side == "left" else "lower"

        if bound == "lower":
            return {full_path: {"lower": literal, "upper": None}}
        return {full_path: {"lower": None, "upper": literal}}

    def bounds_for_condition(condition: exp.Expression, scope) -> dict:
        if isinstance(condition, exp.Paren):
            return bounds_for_condition(condition.this, scope)
        if isinstance(condition, exp.Not):
            inner = condition.this
            if isinstance(inner, exp.Paren):
                inner = inner.this
            if isinstance(inner, exp.GT):
                return bounds_for_comparison(
                    exp.LTE(this=inner.left, expression=inner.right), scope
                )
            if isinstance(inner, exp.GTE):
                return bounds_for_comparison(
                    exp.LT(this=inner.left, expression=inner.right), scope
                )
            if isinstance(inner, exp.LT):
                return bounds_for_comparison(
                    exp.GTE(this=inner.left, expression=inner.right), scope
                )
            if isinstance(inner, exp.LTE):
                return bounds_for_comparison(
                    exp.GT(this=inner.left, expression=inner.right), scope
                )
            return {}
        if isinstance(condition, exp.And):
            return merge_bounds_and(
                bounds_for_condition(condition.left, scope),
                bounds_for_condition(condition.right, scope),
            )
        if isinstance(condition, exp.Or):
            return merge_bounds_or(
                bounds_for_condition(condition.left, scope),
                bounds_for_condition(condition.right, scope),
            )
        if isinstance(
            condition,
            (
                exp.GT,
                exp.GTE,
                exp.LT,
                exp.LTE,
                exp.Between,
                exp.EQ,
                exp.In,
                exp.NEQ,
            ),
        ):
            return bounds_for_comparison(condition, scope)
        return {}

    def merge_bounds_union(left: dict, right: dict) -> dict:
        if not left:
            return right
        if not right:
            return left
        merged: dict[str, dict[str, str | None]] = {}
        for key in set(left) | set(right):
            if key not in left:
                merged[key] = right[key]
                continue
            if key not in right:
                merged[key] = left[key]
                continue
            lower_left = left[key]["lower"]
            lower_right = right[key]["lower"]
            if lower_left is None or lower_right is None:
                lower = None
            else:
                lower = min(lower_left, lower_right)

            upper_left = left[key]["upper"]
            upper_right = right[key]["upper"]
            if upper_left is None or upper_right is None:
                upper = None
            else:
                upper = max(upper_left, upper_right)

            merged[key] = {"lower": lower, "upper": upper}
        return merged

    def analyze_scopes(expression: exp.Expression) -> dict:
        scoped_results: dict[str, dict[str, str | None]] = {}
        for scope in traverse_scope(expression):
            conditions = []
            where = scope.expression.args.get("where")
            if where and where.this:
                conditions.append(where.this)

            qualify = scope.expression.args.get("qualify")
            if qualify and qualify.this:
                conditions.append(qualify.this)

            having = scope.expression.args.get("having")
            if having and having.this:
                conditions.append(having.this)

            for join in scope.expression.args.get("joins", []):
                on = join.args.get("on")
                if not on:
                    continue
                if isinstance(on, exp.Expression):
                    conditions.append(on)

            bounds = {}
            for condition in conditions:
                bounds = merge_bounds_and(
                    bounds, bounds_for_condition(condition, scope)
                )
            scoped_results = merge_bounds_and(scoped_results, bounds)

        for key, value in list(scoped_results.items()):
            lower = value.get("lower")
            upper = value.get("upper")
            if lower is not None and upper is not None and lower > upper:
                scoped_results[key] = {"lower": None, "upper": None}

        return scoped_results

    def analyze_expression(expression: exp.Expression) -> dict:
        if isinstance(expression, exp.Union):
            with_expr = expression.args.get("with")
            left = expression.this.copy()
            right = expression.expression.copy()
            if with_expr:
                left.set("with", with_expr)
                right.set("with", with_expr)
            left_bounds = analyze_expression(left)
            right_bounds = analyze_expression(right)
            return merge_bounds_union(left_bounds, right_bounds)
        return analyze_scopes(expression)

    return analyze_expression(qualified)


def _add(references: dict[str, set[str]], table: str, column: str):
    if table in references:
        references[table].add(column)
    else:
        references[table] = {column}
