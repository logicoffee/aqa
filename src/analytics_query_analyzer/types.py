from typing import TypedDict


class ReferenceRow(TypedDict):
    database: str
    schema: str
    table: str
    column: str


class TimespanRow(ReferenceRow):
    lower: str | None
    upper: str | None
