from sqlglot import dialects

SUPPORTED_DIALECTS = {dialects.BigQuery}


def build_schema(
    dialect: str | type[dialects.Dialect],
    database: str,
    schema: str | None,
    table: str | None,
):
    resolved = (
        dialects.get_or_raise(dialect.lower()) if isinstance(dialect, str) else dialect
    )
    if resolved not in SUPPORTED_DIALECTS:
        raise ValueError(f"Unsupported dialect for build_schema: {resolved.__name__}")
    return _build_schema_bigquery(database, schema, table)


def _build_schema_bigquery(project: str, dataset: str | None, table: str | None):
    try:
        from google.cloud import bigquery  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "BigQuery support is not installed. "
            "Install with: pip install analytics-query-analyzer[bigquery]"
        ) from e

    def _format_field_type(field) -> str:
        if field.field_type == "RECORD":
            parts = [
                f"{child.name} {_format_field_type(child)}" for child in field.fields
            ]
            return f"struct<{', '.join(parts)}>"
        return field.field_type.lower()

    def _field_to_schema(field) -> dict | str:
        if field.mode == "REPEATED":
            return f"array<{_format_field_type(field)}>"
        if field.field_type == "RECORD":
            return {child.name: _field_to_schema(child) for child in field.fields}
        return field.field_type.lower()

    def _table_to_schema(table_obj: bigquery.Table) -> dict:
        return {
            table_obj.table_id: {
                field.name: _field_to_schema(field) for field in table_obj.schema
            }
        }

    def _dataset_to_schema(dataset_id: str) -> dict:
        dataset_ref = bigquery.DatasetReference(project, dataset_id)
        table_schema = {}
        for table_item in client.list_tables(dataset_ref):
            table_obj = client.get_table(table_item)
            table_schema.update(_table_to_schema(table_obj))
        return {dataset_id: table_schema}

    client = bigquery.Client(project=project)
    if dataset is None:
        result = {}
        for ds in client.list_datasets():
            result.update(_dataset_to_schema(ds.dataset_id))
        return {project: result}
    elif table is None:
        return {project: _dataset_to_schema(dataset)}
    else:
        dataset_ref = bigquery.DatasetReference(project, dataset)
        table_ref = dataset_ref.table(table)
        table_obj = client.get_table(table_ref)
        return {project: {dataset: _table_to_schema(table_obj)}}
