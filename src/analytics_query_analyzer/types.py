from datetime import date
from typing import TypedDict


class ReferenceRow(TypedDict):
    database: str
    schema: str
    table: str
    column: str | None


class TimeboundsRow(ReferenceRow):
    lower: date | str | None
    upper: date | str | None
