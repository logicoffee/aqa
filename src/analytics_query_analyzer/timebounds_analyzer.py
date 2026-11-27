import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Callable, TypeAlias, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlglot import dialects, exp
from sqlglot.optimizer.scope import traverse_scope

from .column_resolver import resolve_column_path
from .types import TimeboundsRow


class TimeboundsBounds(TypedDict):
    lower: date | str | None
    upper: date | str | None


TimeboundsResults: TypeAlias = dict[str, TimeboundsBounds]


class TimeboundsAnalyzer:
    def __init__(
        self,
        schema: dict,
        default_catalog: str,
        current_date_provider: Callable[[], str | date | datetime] | None = None,
        dialect: type[dialects.Dialect] | None = None,
    ):
        self.schema = schema
        self.dialect = dialect
        self.default_catalog = default_catalog
        self.current_date_provider = current_date_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def analyze(self, expression: exp.Expression) -> list[TimeboundsRow]:
        return _flatten_timebounds(self._analyze_internal(expression))

    def _analyze_internal(self, expression: exp.Expression) -> TimeboundsResults:
        return self.analyze_scopes(expression)

    def analyze_scopes(self, expression: exp.Expression) -> TimeboundsResults:
        scopes = list(traverse_scope(expression))
        scope_bounds = {}
        reads = []
        for scope in scopes:
            conditions = []
            for name in ("where", "qualify", "having"):
                clause = scope.expression.args.get(name)
                if clause and clause.this:
                    conditions.append(clause.this)

            joins = scope.expression.args.get("joins", [])
            # ON predicates of outer joins do not filter their preserved side.
            if not any(join.args.get("side") for join in joins):
                conditions.extend(
                    join.args["on"] for join in joins if join.args.get("on")
                )

            bounds = {}
            for condition in conditions:
                bounds = self.merge_bounds_and(
                    bounds, self.bounds_for_condition(condition, scope)
                )
            scope_bounds[id(scope)] = bounds

            # selected_sources excludes visible but unused CTEs.
            for _, (_, source) in scope.selected_sources.items():
                if not isinstance(source, exp.Table):
                    continue
                project = source.catalog or self.default_catalog
                dataset = source.db
                if not dataset:
                    matches = [
                        name
                        for name, tables in self.schema.get(project, {}).items()
                        if source.name in tables
                    ]
                    if len(matches) != 1:
                        continue
                    dataset = matches[0]
                reads.append((scope, f"{project}.{dataset}.{source.name}."))

        keys = {key for bounds in scope_bounds.values() for key in bounds}
        direct_reads = {}
        for scope, prefix in reads:
            direct_reads.setdefault(id(scope), []).append(prefix)

        def collect(scope, stack):
            if id(scope) in stack:
                return []
            stack = stack | {id(scope)}
            items = [(prefix, {}) for prefix in direct_reads.get(id(scope), [])]
            children = [
                source
                for _, source in scope.selected_sources.values()
                if not isinstance(source, exp.Table)
                and hasattr(source, "selected_sources")
            ]
            children += list(
                getattr(
                    scope, "union_scopes", getattr(scope, "set_operation_scopes", [])
                )
            ) + list(scope.subquery_scopes)
            for child in children:
                items.extend(collect(child, stack))
            for key, value in scope_bounds[id(scope)].items():
                matches = [
                    i for i, (prefix, _) in enumerate(items) if key.startswith(prefix)
                ]
                if len(matches) == 1:
                    i = matches[0]
                    prefix, bounds = items[i]
                    items[i] = (prefix, self.merge_bounds_and(bounds, {key: value}))
            return items

        all_reads = collect(scopes[-1], set()) if scopes else []
        result: TimeboundsResults = {}
        for key in keys:
            matching_reads = [
                bounds.get(key, {"lower": None, "upper": None})
                for prefix, bounds in all_reads
                if key.startswith(prefix)
            ]
            for value in matching_reads:
                if (
                    value["lower"] is not None
                    and value["upper"] is not None
                    and value["lower"] > value["upper"]
                ):
                    value = {"lower": None, "upper": None}
                if key not in result:
                    result[key] = value
                else:
                    result = self.merge_bounds_union(result, {key: value})
        return result

    def bounds_for_condition(
        self, condition: exp.Expression, scope
    ) -> TimeboundsResults:
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
    ) -> TimeboundsResults:
        if isinstance(comparison, exp.Between):
            if comparison.this.find(exp.AggFunc) or comparison.this.find(exp.Window):
                return {}
            column = self.extract_column(comparison.this)
            low = self.extract_literal(comparison.args.get("low"))
            high = self.extract_literal(comparison.args.get("high"))
            if not column:
                return {}
            resolved = resolve_column_path(
                column,
                scope,
                self.default_catalog,
                self.schema,
                self.extract_lineage_column,
            )
            if not resolved:
                return {}
            full_path, column_path = resolved
            project, dataset, table, _ = full_path.split(".", 3)
            if self.is_table_suffix(table, column_path):
                low = self._extract_suffix_literal(comparison.args.get("low"))
                high = self._extract_suffix_literal(comparison.args.get("high"))
            elif not self.is_time_column(project, dataset, table, column_path):
                return {}
            if low is None and high is None:
                return {full_path: {"lower": None, "upper": None}}
            return {full_path: {"lower": low, "upper": high}}

        if isinstance(comparison, exp.In):
            if comparison.this.find(exp.AggFunc) or comparison.this.find(exp.Window):
                return {}
            column = self.extract_column(comparison.this)
            if not column:
                return {}
            resolved = resolve_column_path(
                column,
                scope,
                self.default_catalog,
                self.schema,
                self.extract_lineage_column,
            )
            if not resolved:
                return {}
            full_path, column_path = resolved
            project, dataset, table, _ = full_path.split(".", 3)
            if self.is_table_suffix(table, column_path):
                literals = [
                    self._extract_suffix_literal(value)
                    for value in comparison.expressions
                ]
            elif self.is_time_column(project, dataset, table, column_path):
                literals = [
                    self.extract_literal(value) for value in comparison.expressions
                ]
            else:
                return {}
            if any(value is None for value in literals):
                return {full_path: {"lower": None, "upper": None}}
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
        # DATE_DIFF(constant, date_column, DAY) reverses the comparison.
        if (
            self.dialect is dialects.BigQuery
            and isinstance(left, exp.DateDiff)
            and isinstance(comparison, (exp.LTE, exp.LT))
        ):
            unit = self._extract_unit_literal(left.args.get("unit"))
            base = self.extract_literal(left.this)
            days = self._extract_int_literal(right)
            column = self.extract_column(left.expression)
            if unit == "DAY" and base is not None and days is not None and column:
                resolved = resolve_column_path(
                    column,
                    scope,
                    self.default_catalog,
                    self.schema,
                    self.extract_lineage_column,
                )
                if resolved:
                    full_path, column_path = resolved
                    project, dataset, table, _ = full_path.split(".", 3)
                    column_type = (
                        self.schema.get(project, {})
                        .get(dataset, {})
                        .get(table, {})
                        .get(column_path)
                    )
                    if self.is_time_column(project, dataset, table, column_path):
                        # Whole-unit differences on timestamps can include part of
                        # the preceding day; widen the calendar envelope.
                        extra_day = 0 if str(column_type).lower() == "date" else 1
                        try:
                            return {
                                full_path: {
                                    "lower": base - timedelta(days=days + extra_day),
                                    "upper": None,
                                }
                            }
                        except OverflowError:
                            return {}
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
            column,
            scope,
            self.default_catalog,
            self.schema,
            self.extract_lineage_column,
        )
        if not resolved:
            return {}
        full_path, column_path = resolved
        project, dataset, table, _ = full_path.split(".", 3)
        if self.is_table_suffix(table, column_path):
            column_expr = left if column_side == "left" else right
            if not isinstance(column_expr, exp.Column):
                return {}
            literal = self._extract_suffix_literal(
                right if column_side == "left" else left
            )
        elif not self.is_time_column(project, dataset, table, column_path):
            return {}
        if trunc_unit and literal is not None:
            literal = self._truncate_date(literal, trunc_unit)
        if literal is None:
            return {full_path: {"lower": None, "upper": None}}

        if isinstance(comparison, exp.NEQ):
            return {full_path: {"lower": None, "upper": None}}

        column_expr = left if column_side == "left" else right
        aggregate = (
            column_expr.this if isinstance(column_expr, exp.Window) else column_expr
        )
        if column_expr.find(exp.AggFunc) or column_expr.find(exp.Window):
            min_lower = (
                isinstance(aggregate, exp.Min)
                and not (
                    isinstance(column_expr, exp.Window) and column_expr.args.get("spec")
                )
                and (
                    (
                        column_side == "left"
                        and isinstance(comparison, (exp.GT, exp.GTE))
                    )
                    or (
                        column_side == "right"
                        and isinstance(comparison, (exp.LT, exp.LTE))
                    )
                )
            )
            if not min_lower:
                return {full_path: {"lower": None, "upper": None}}

        if isinstance(comparison, exp.EQ):
            if trunc_unit:
                end = self._truncated_period_end(literal, trunc_unit)
                if end is None:
                    return {full_path: {"lower": None, "upper": None}}
                return {full_path: {"lower": literal, "upper": end}}
            return {full_path: {"lower": literal, "upper": literal}}

        if isinstance(comparison, (exp.GT, exp.GTE)):
            bound = "lower" if column_side == "left" else "upper"
        else:
            bound = "upper" if column_side == "left" else "lower"

        if bound == "lower":
            return {full_path: {"lower": literal, "upper": None}}
        if trunc_unit:
            literal = self._truncated_period_end(literal, trunc_unit)
        return {full_path: {"lower": None, "upper": literal}}

    def _truncated_period_end(self, value: date, unit: str) -> date | None:
        unit = unit.strip().upper()
        if unit in {"MONTH", "MON", "YEAR", "YYYY", "QUARTER", "QTR"}:
            months = (
                1 if unit in {"MONTH", "MON"} else 12 if unit in {"YEAR", "YYYY"} else 3
            )
            try:
                return self._shift_month(value, months) - timedelta(days=1)
            except (OverflowError, ValueError):
                return None
        if unit == "WEEK":
            try:
                return value + timedelta(days=6)
            except OverflowError:
                return None
        return value if unit == "DAY" else None

    def extract_column(self, expr: exp.Expression) -> exp.Column | None:
        if isinstance(expr, exp.Column):
            return expr
        if isinstance(expr, exp.Dot) and isinstance(expr.expression, exp.Identifier):
            return self.extract_column(expr.this)
        if isinstance(expr, exp.Cast):
            target = expr.args.get("to")
            if not isinstance(target, exp.DataType) or target.this not in {
                exp.DataType.Type.DATE,
                exp.DataType.Type.DATETIME,
                exp.DataType.Type.TIMESTAMP,
                exp.DataType.Type.TIMESTAMPTZ,
            }:
                return None
            return self.extract_column(expr.this)
        if isinstance(expr, exp.Date) and expr.args.get("zone"):
            return None
        if isinstance(expr, (exp.Date, exp.Min)):
            return self.extract_column(expr.this)
        if isinstance(expr, exp.Paren):
            return self.extract_column(expr.this)
        if expr.find(exp.Window):
            return None
        return None

    def extract_lineage_column(self, expr: exp.Expression) -> exp.Column | None:
        # An aggregate is not an identity projection: an outer filter on its
        # result does not generally constrain every input row.
        if expr.find(exp.AggFunc) or expr.find(exp.Window):
            return None
        return self.extract_column(expr)

    def extract_window_column(self, expr: exp.Expression) -> exp.Column | None:
        if not isinstance(expr, exp.Window):
            return None
        if expr.this is None:
            return None
        columns = list(expr.this.find_all(exp.Column))
        if len(columns) == 1:
            return columns[0]
        return None

    def extract_literal(self, expr: exp.Expression | None) -> date | None:
        if expr is None:
            return None
        if isinstance(expr, exp.Literal):
            if expr.is_string:
                return _normalize_iso_date(expr.this)
            return None
        if isinstance(expr, (exp.CurrentDate, exp.CurrentDatetime)):
            return self._evaluate_current_date(expr.args.get("this"))
        if isinstance(expr, exp.CurrentTimestamp):
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
        if isinstance(expr, exp.Timestamp) and expr.args.get("zone"):
            value = self._extract_string_literal(expr.this)
            zone = self._extract_string_literal(expr.args.get("zone"))
            if value is None or zone is None:
                return None
            try:
                timestamp = datetime.fromisoformat(value)
                if timestamp.tzinfo is not None:
                    return None
                return (
                    timestamp.replace(tzinfo=ZoneInfo(zone))
                    .astimezone(timezone.utc)
                    .date()
                )
            except (ValueError, ZoneInfoNotFoundError, OverflowError):
                return None
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
        if isinstance(expr, (exp.DateAdd, exp.DateSub, exp.TsOrDsAdd)):
            return self._extract_date_arithmetic(expr)
        if isinstance(expr, (exp.Add, exp.Sub)):
            return self._extract_interval_arithmetic(expr)
        return None

    def _evaluate_current_date(
        self, zone_expr: exp.Expression | None = None
    ) -> date | None:
        value = self.current_date_provider()
        if isinstance(value, datetime):
            if zone_expr is not None:
                zone_name = self._extract_string_literal(zone_expr)
                if zone_name is None or value.tzinfo is None:
                    return None
                try:
                    value = value.astimezone(ZoneInfo(zone_name))
                except (ValueError, ZoneInfoNotFoundError):
                    return None
            elif value.tzinfo is not None:
                value = value.astimezone(timezone.utc)
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
        try:
            return date(year, month, day)
        except ValueError:
            return None

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
            parsed = datetime.strptime(value_str, format_str)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc)
            return parsed.date()
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

    def _extract_interval_arithmetic(self, expr: exp.Expression) -> date | None:
        left = expr.args.get("this")
        right = expr.args.get("expression")
        if isinstance(right, exp.Interval):
            base = self.extract_literal(left)
            delta = self._extract_int_literal(right.args.get("this"))
            unit = self._extract_unit_literal(right.args.get("unit"))
            if base is None or delta is None or not unit:
                return None
            if isinstance(expr, exp.Sub):
                delta = -delta
            return self._apply_date_delta(base, delta, unit)
        if isinstance(left, exp.Interval):
            base = self.extract_literal(right)
            delta = self._extract_int_literal(left.args.get("this"))
            unit = self._extract_unit_literal(left.args.get("unit"))
            if base is None or delta is None or not unit:
                return None
            return self._apply_date_delta(base, delta, unit)
        return None

    def _extract_trunc_date(self, expr: exp.Expression) -> date | None:
        if expr.args.get("zone"):
            return None
        target = expr.args.get("this") or expr.this
        unit_expr = expr.args.get("unit") or expr.args.get("part")
        value = self.extract_literal(target)
        unit = self._extract_unit_literal(unit_expr)
        if value is None or not unit:
            return None
        return self._truncate_date(value, unit)

    def _extract_suffix_literal(self, expr: exp.Expression | None) -> str | None:
        literal = self._extract_string_literal(expr)
        if literal is not None:
            return literal
        if not isinstance(expr, exp.TimeToStr):
            return None
        pattern = self._extract_string_literal(expr.args.get("format"))
        if pattern not in {"%Y%m%d", "%Y-%m-%d"}:
            return None
        target = expr.this
        if isinstance(target, exp.TsOrDsToDate):
            target = target.this
        value = self.extract_literal(target)
        if value is None:
            return None
        if pattern == "%Y%m%d":
            return f"{value.year:04d}{value.month:02d}{value.day:02d}"
        return value.isoformat()

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
                try:
                    return int(float(expr.this))
                except (TypeError, ValueError):
                    return None
        if isinstance(expr, exp.Neg):
            value = self._extract_int_literal(expr.this)
            return None if value is None else -value
        if isinstance(expr, exp.Cast):
            return self._extract_int_literal(expr.this)
        if isinstance(expr, exp.Paren):
            return self._extract_int_literal(expr.this)
        return None

    def _extract_trunc_column(
        self, expr: exp.Expression
    ) -> tuple[exp.Column | None, str | None]:
        trunc_types = (exp.DateTrunc, exp.DatetimeTrunc, exp.TimestampTrunc)
        if not isinstance(expr, trunc_types) or expr.args.get("zone"):
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
            week_start = (
                (parsed.weekday() + 1) % 7
                if self.dialect is dialects.BigQuery
                else parsed.weekday()
            )
            try:
                return parsed - timedelta(days=week_start)
            except OverflowError:
                return None
        if unit in {"DAY"}:
            return parsed
        return None

    def _apply_date_delta(self, value: date, delta: int, unit: str) -> date | None:
        unit = unit.strip().upper()
        try:
            if unit in {"DAY", "DAYS"}:
                return value + timedelta(days=delta)
            if unit in {"WEEK", "WEEKS"}:
                return value + timedelta(weeks=delta)
            if unit in {"MONTH", "MONTHS"}:
                return self._shift_month(value, delta)
            if unit in {"YEAR", "YEARS"}:
                return self._shift_month(value, delta * 12)
        except (OverflowError, ValueError):
            return None
        return None

    @staticmethod
    def _shift_month(date_value: date, months: int) -> date | None:
        year = date_value.year + (date_value.month - 1 + months) // 12
        month = (date_value.month - 1 + months) % 12 + 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(date_value.day, last_day)
        return date(year, month, day)

    def is_table_suffix(self, table: str, column: str) -> bool:
        return (
            self.dialect is dialects.BigQuery
            and table.endswith("*")
            and column.lower() == "_table_suffix"
        )

    def is_time_column(
        self, project: str, dataset: str, table: str, column_name: str
    ) -> bool:
        if self.dialect is dialects.BigQuery and column_name.lower() in {
            "_partitiondate",
            "_partitiontime",
        }:
            return True
        try:
            column_type = self.schema[project][dataset][table]
            for part in column_name.split("."):
                column_type = column_type[part]
        except (KeyError, TypeError):
            return False
        normalized = str(column_type).lower()
        if normalized in {
            "datetime",
            "date",
            "timestamp",
            "timestamp without time zone",
            "timestamp with time zone",
        }:
            return True
        return False

    @staticmethod
    def merge_bounds_and(
        left: TimeboundsResults, right: TimeboundsResults
    ) -> TimeboundsResults:
        merged: TimeboundsResults = {}
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
        left: TimeboundsResults, right: TimeboundsResults
    ) -> TimeboundsResults:
        merged: TimeboundsResults = {}
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
        left: TimeboundsResults, right: TimeboundsResults
    ) -> TimeboundsResults:
        if not left:
            return right
        if not right:
            return left
        merged: TimeboundsResults = {}
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
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.date()
    except (ValueError, OverflowError):
        return None


def _flatten_timebounds(
    results: TimeboundsResults,
) -> list[TimeboundsRow]:
    rows: list[TimeboundsRow] = []
    for full_path, bounds in results.items():
        database, schema, table, column = full_path.split(".", 3)
        rows.append(
            TimeboundsRow(
                database=database,
                schema=schema,
                table=table,
                column=column,
                lower=bounds.get("lower"),
                upper=bounds.get("upper"),
            )
        )
    rows.sort(
        key=lambda row: (
            row["database"] or "",
            row["schema"] or "",
            row["table"] or "",
            row["column"] or "",
        )
    )
    return rows
