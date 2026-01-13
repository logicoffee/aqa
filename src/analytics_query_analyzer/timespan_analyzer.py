import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Callable, TypeAlias, TypedDict

from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from .column_resolver import resolve_column_path


class TimespanBounds(TypedDict):
    lower: date | None
    upper: date | None


TimespanResults: TypeAlias = dict[str, TimespanBounds]


class TimespanAnalyzer:
    def __init__(
        self,
        schema: dict,
        default_project: str,
        current_date_provider: Callable[[], str | date | datetime] | None = None,
    ):
        self.schema = schema
        self.default_project = default_project
        self.current_date_provider = current_date_provider or date.today

    def analyze(self, expression: exp.Expression) -> dict[str, dict[str, str | None]]:
        return _stringify_results(self._analyze_internal(expression))

    def _analyze_internal(self, expression: exp.Expression) -> TimespanResults:
        if isinstance(expression, exp.Union):
            with_expr = expression.args.get("with")
            left = expression.this.copy()
            right = expression.expression.copy()
            if with_expr:
                left.set("with", with_expr)
                right.set("with", with_expr)
            left_bounds = self._analyze_internal(left)
            right_bounds = self._analyze_internal(right)
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
        left_column, left_trunc_unit = self._extract_trunc_column(left)
        right_column, right_trunc_unit = self._extract_trunc_column(right)
        if left_column is None:
            left_column = self.extract_column(left)
        if right_column is None:
            right_column = self.extract_column(right)
        column_side = None
        column = None
        trunc_unit = None
        if left_column:
            column = left_column
            column_side = "left"
            trunc_unit = left_trunc_unit
        elif right_column:
            column = right_column
            column_side = "right"
            trunc_unit = right_trunc_unit
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
        if trunc_unit and literal is not None:
            literal = self._truncate_date(literal, trunc_unit)
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

    def extract_literal(self, expr: exp.Expression) -> date | None:
        if isinstance(expr, exp.Literal):
            if expr.is_string:
                return _normalize_iso_date(expr.this)
            return None
        if isinstance(expr, exp.CurrentDate):
            return self._evaluate_current_date()
        if isinstance(expr, (exp.CurrentDatetime, exp.CurrentTimestamp)):
            return self._evaluate_current_date()
        if isinstance(expr, exp.TsOrDsToDatetime):
            return self.extract_literal(expr.this)
        if isinstance(expr, exp.Cast):
            target = expr.args.get("to")
            if isinstance(target, exp.DataType):
                target_type = target.this
                if isinstance(target_type, exp.DataType.Type):
                    target_name = target_type.value
                else:
                    target_name = str(target_type)
                if target_name in {"DATE", "DATETIME", "TIMESTAMP", "TIMESTAMPTZ"}:
                    return self.extract_literal(expr.this)
                return None
            return self.extract_literal(expr.this)
        if isinstance(expr, exp.Paren):
            return self.extract_literal(expr.this)
        if isinstance(expr, (exp.Date, exp.Datetime, exp.Timestamp, exp.Time)):
            return self.extract_literal(expr.this)
        trunc_types = (exp.DateTrunc, exp.DatetimeTrunc, exp.TimestampTrunc)
        if isinstance(expr, trunc_types):
            return self._extract_trunc_date(expr)
        parse_types = (
            exp.ParseDatetime,
            exp.StrToDate,
            exp.StrToTime,
        )
        if isinstance(expr, parse_types):
            return self._extract_parsed_date(expr)
        parts_types = (
            exp.DateFromParts,
            exp.TimestampFromParts,
        )
        if isinstance(expr, parts_types):
            return self._extract_parts_date(expr)
        if isinstance(expr, exp.UnixToTime):
            return self._extract_epoch_date(expr)
        if isinstance(expr, (exp.DateAdd, exp.DateSub)):
            return self._extract_date_arithmetic(expr)
        return None

    def _evaluate_current_date(self) -> date | None:
        if self.current_date_provider is None:
            return None
        value = self.current_date_provider()
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return _normalize_iso_date(value)
        return None

    def _extract_parts_date(self, expr: exp.Expression) -> date | None:
        year = self._extract_int_literal(expr.args.get("year"))
        month = self._extract_int_literal(expr.args.get("month"))
        day = self._extract_int_literal(expr.args.get("day"))
        if year is None or month is None or day is None:
            return None
        return self._format_date_parts(year, month, day)

    @staticmethod
    def _format_date_parts(year: int, month: int, day: int) -> date | None:
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        return date(year, month, day)

    def _extract_parsed_date(self, expr: exp.Expression) -> date | None:
        format_expr = expr.args.get("format") or expr.args.get("format_string")
        string_expr = expr.args.get("string") or expr.args.get("this")
        if format_expr is None or string_expr is None:
            expressions = expr.expressions
            if len(expressions) >= 2:
                string_expr = expressions[0]
                format_expr = expressions[1]
        format_str = self._extract_string_literal(format_expr)
        value_str = self._extract_string_literal(string_expr)
        if not format_str or not value_str:
            return None
        try:
            return datetime.strptime(value_str, format_str).date()
        except ValueError:
            return None

    def _extract_epoch_date(self, expr: exp.Expression) -> date | None:
        value = self._extract_int_literal(expr.args.get("this") or expr.this)
        if value is None:
            return None
        scale = self._extract_int_literal(expr.args.get("scale"))
        if scale == 3:
            value = value / 1000
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None

    def _extract_date_arithmetic(self, expr: exp.Expression) -> date | None:
        base = self.extract_literal(expr.args.get("this") or expr.this)
        if base is None:
            return None
        delta_value = self._extract_int_literal(expr.args.get("expression"))
        if delta_value is None:
            return None
        unit = self._extract_unit_literal(expr.args.get("unit"))
        if not unit:
            return None
        if isinstance(expr, exp.DateSub):
            delta_value = -delta_value
        return self._apply_date_delta(base, delta_value, unit)

    def _extract_trunc_date(self, expr: exp.Expression) -> date | None:
        target = expr.args.get("this") or expr.this
        unit_expr = expr.args.get("unit") or expr.args.get("part")
        value = self.extract_literal(target)
        unit = self._extract_unit_literal(unit_expr)
        if value is None or not unit:
            return None
        return self._truncate_date(value, unit)

    def _extract_string_literal(self, expr: exp.Expression | None) -> str | None:
        if expr is None:
            return None
        if isinstance(expr, exp.Literal) and expr.is_string:
            return expr.this
        if isinstance(expr, exp.Cast):
            return self._extract_string_literal(expr.this)
        if isinstance(expr, exp.Paren):
            return self._extract_string_literal(expr.this)
        return None

    def _extract_unit_literal(self, expr: exp.Expression | None) -> str | None:
        if expr is None:
            return None
        if isinstance(expr, exp.Var):
            return expr.this.upper()
        literal = self._extract_string_literal(expr)
        if literal:
            return literal.upper()
        return str(expr).upper()

    def _extract_int_literal(self, expr: exp.Expression | None) -> int | None:
        if expr is None:
            return None
        if isinstance(expr, exp.Literal):
            try:
                return int(expr.this)
            except (TypeError, ValueError):
                return None
        if isinstance(expr, exp.Cast):
            return self._extract_int_literal(expr.this)
        if isinstance(expr, exp.Paren):
            return self._extract_int_literal(expr.this)
        return None

    def _extract_trunc_column(
        self, expr: exp.Expression
    ) -> tuple[exp.Column | None, str | None]:
        trunc_types = (exp.DateTrunc, exp.DatetimeTrunc, exp.TimestampTrunc)
        if not isinstance(expr, trunc_types):
            return None, None
        target = expr.args.get("this") or expr.this
        unit_expr = expr.args.get("unit") or expr.args.get("part")
        column = self.extract_column(target)
        unit = self._extract_unit_literal(unit_expr)
        return column, unit

    def _truncate_date(self, value: date, unit: str) -> date | None:
        parsed = value
        unit = unit.strip().upper()
        if unit in {"YEAR", "YYYY"}:
            return date(parsed.year, 1, 1)
        if unit in {"QUARTER", "QTR"}:
            quarter_start = ((parsed.month - 1) // 3) * 3 + 1
            return date(parsed.year, quarter_start, 1)
        if unit in {"MONTH", "MON"}:
            return date(parsed.year, parsed.month, 1)
        if unit in {"WEEK"}:
            monday = parsed - timedelta(days=parsed.weekday())
            return monday
        if unit in {"DAY"}:
            return parsed
        return None

    def _apply_date_delta(self, value: date, delta: int, unit: str) -> date | None:
        parsed = value
        unit = unit.strip().upper()
        if unit in {"DAY", "DAYS"}:
            return parsed + timedelta(days=delta)
        if unit in {"WEEK", "WEEKS"}:
            return parsed + timedelta(weeks=delta)
        if unit in {"MONTH", "MONTHS"}:
            return self._shift_month(parsed, delta)
        if unit in {"YEAR", "YEARS"}:
            return self._shift_month(parsed, delta * 12)
        return None

    @staticmethod
    def _shift_month(date_value: date, months: int) -> date | None:
        year = date_value.year + (date_value.month - 1 + months) // 12
        month = (date_value.month - 1 + months) % 12 + 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(date_value.day, last_day)
        return date(year, month, day)

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


def _normalize_iso_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _stringify_results(results: TimespanResults) -> dict[str, dict[str, str | None]]:
    output: dict[str, dict[str, str | None]] = {}
    for key, bounds in results.items():
        output[key] = {
            "lower": bounds["lower"].isoformat() if bounds["lower"] else None,
            "upper": bounds["upper"].isoformat() if bounds["upper"] else None,
        }
    return output
