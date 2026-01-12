from typing import TypeAlias

from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from .column_resolver import resolve_column_path

TimespanBounds: TypeAlias = dict[str, str | None]
TimespanResults: TypeAlias = dict[str, TimespanBounds]


class TimespanAnalyzer:
    def __init__(self, schema: dict, default_project: str):
        self.schema = schema
        self.default_project = default_project

    def analyze(self, expression: exp.Expression) -> TimespanResults:
        if isinstance(expression, exp.Union):
            with_expr = expression.args.get("with")
            left = expression.this.copy()
            right = expression.expression.copy()
            if with_expr:
                left.set("with", with_expr)
                right.set("with", with_expr)
            left_bounds = self.analyze(left)
            right_bounds = self.analyze(right)
            return self.merge_bounds_union(left_bounds, right_bounds)
        return self.analyze_scopes(expression)

    def analyze_scopes(self, expression: exp.Expression) -> TimespanResults:
        scoped_results: TimespanResults = {}
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
                bounds = self.merge_bounds_and(
                    bounds, self.bounds_for_condition(condition, scope)
                )
            scoped_results = self.merge_bounds_and(scoped_results, bounds)

        for key, value in list(scoped_results.items()):
            lower = value.get("lower")
            upper = value.get("upper")
            if lower is not None and upper is not None and lower > upper:
                scoped_results[key] = {"lower": None, "upper": None}

        return scoped_results

    def bounds_for_condition(self, condition: exp.Expression, scope) -> TimespanResults:
        if isinstance(condition, exp.Paren):
            return self.bounds_for_condition(condition.this, scope)
        if isinstance(condition, exp.Not):
            inner = condition.this
            if isinstance(inner, exp.Paren):
                inner = inner.this
            if isinstance(inner, exp.GT):
                return self.bounds_for_comparison(
                    exp.LTE(this=inner.left, expression=inner.right), scope
                )
            if isinstance(inner, exp.GTE):
                return self.bounds_for_comparison(
                    exp.LT(this=inner.left, expression=inner.right), scope
                )
            if isinstance(inner, exp.LT):
                return self.bounds_for_comparison(
                    exp.GTE(this=inner.left, expression=inner.right), scope
                )
            if isinstance(inner, exp.LTE):
                return self.bounds_for_comparison(
                    exp.GT(this=inner.left, expression=inner.right), scope
                )
            return {}
        if isinstance(condition, exp.And):
            return self.merge_bounds_and(
                self.bounds_for_condition(condition.left, scope),
                self.bounds_for_condition(condition.right, scope),
            )
        if isinstance(condition, exp.Or):
            return self.merge_bounds_or(
                self.bounds_for_condition(condition.left, scope),
                self.bounds_for_condition(condition.right, scope),
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
            return self.bounds_for_comparison(condition, scope)
        return {}

    def bounds_for_comparison(
        self, comparison: exp.Expression, scope
    ) -> TimespanResults:
        if isinstance(comparison, exp.Between):
            column = self.extract_column(comparison.this)
            low = self.extract_literal(comparison.args.get("low"))
            high = self.extract_literal(comparison.args.get("high"))
            if not column:
                return {}
            resolved = resolve_column_path(
                column, scope, self.default_project, self.schema, self.extract_column
            )
            if not resolved:
                return {}
            full_path, column_path = resolved
            project, dataset, table, _ = full_path.split(".", 3)
            if not self.is_time_column(project, dataset, table, column_path):
                return {}
            if low is None and high is None:
                return {full_path: {"lower": None, "upper": None}}
            return {full_path: {"lower": low, "upper": high}}

        if isinstance(comparison, exp.In):
            column = self.extract_column(comparison.this)
            if not column:
                return {}
            resolved = resolve_column_path(
                column, scope, self.default_project, self.schema, self.extract_column
            )
            if not resolved:
                return {}
            full_path, column_path = resolved
            project, dataset, table, _ = full_path.split(".", 3)
            if not self.is_time_column(project, dataset, table, column_path):
                return {}
            literals = [self.extract_literal(value) for value in comparison.expressions]
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
        left_column = self.extract_column(left)
        right_column = self.extract_column(right)
        column_side = None
        column = None
        if left_column:
            column = left_column
            column_side = "left"
        elif right_column:
            column = right_column
            column_side = "right"
        else:
            left_window_column = self.extract_window_column(left)
            right_window_column = self.extract_window_column(right)
            if left_window_column:
                column = left_window_column
                column_side = "left"
            elif right_window_column:
                column = right_window_column
                column_side = "right"
        literal = (
            self.extract_literal(right)
            if column_side == "left"
            else self.extract_literal(left)
        )
        if not column:
            return {}

        resolved = resolve_column_path(
            column, scope, self.default_project, self.schema, self.extract_column
        )
        if not resolved:
            return {}
        full_path, column_path = resolved
        project, dataset, table, _ = full_path.split(".", 3)
        if not self.is_time_column(project, dataset, table, column_path):
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

    def extract_column(self, expr: exp.Expression) -> exp.Column | None:
        if isinstance(expr, exp.Column):
            return expr
        if isinstance(expr, exp.Cast):
            return self.extract_column(expr.this)
        if isinstance(expr, exp.Paren):
            return self.extract_column(expr.this)
        if expr.find(exp.Window):
            return None
        columns = list(expr.find_all(exp.Column))
        if len(columns) == 1:
            return columns[0]
        return None

    def extract_window_column(self, expr: exp.Expression) -> exp.Column | None:
        if not isinstance(expr, exp.Window):
            return None
        if expr.this is None:
            return None
        columns = list(expr.this.find_all(exp.Column))
        if len(columns) == 1:
            return columns[0]
        return None

    def extract_literal(self, expr: exp.Expression) -> str | None:
        if isinstance(expr, exp.Literal):
            return expr.this
        if isinstance(expr, exp.Cast):
            return self.extract_literal(expr.this)
        if isinstance(expr, exp.Paren):
            return self.extract_literal(expr.this)
        if isinstance(expr, (exp.Date, exp.Timestamp, exp.Time)):
            return self.extract_literal(expr.this)
        return None

    def is_time_column(
        self, project: str, dataset: str, table: str, column_name: str
    ) -> bool:
        column_root = column_name.split(".", 1)[0]
        try:
            column_type = self.schema[project][dataset][table][column_root]
        except KeyError:
            return False
        return str(column_type).lower() in {"datetime", "date", "timestamp"}

    @staticmethod
    def merge_bounds_and(
        left: TimespanResults, right: TimespanResults
    ) -> TimespanResults:
        merged: TimespanResults = {}
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

    @staticmethod
    def merge_bounds_or(
        left: TimespanResults, right: TimespanResults
    ) -> TimespanResults:
        merged: TimespanResults = {}
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

    @staticmethod
    def merge_bounds_union(
        left: TimespanResults, right: TimespanResults
    ) -> TimespanResults:
        if not left:
            return right
        if not right:
            return left
        merged: TimespanResults = {}
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
