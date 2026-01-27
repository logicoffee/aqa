from datetime import date
from typing import TypedDict


class ReferenceRow(TypedDict):
    database: str
    schema: str
    table: str
    column: str


class TimeboundsRow(ReferenceRow):
    lower: date | None
    upper: date | None
