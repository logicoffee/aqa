import os

from sqlglot import dialects

SUPPORTED_DIALECTS = {dialects.BigQuery, dialects.Redshift}


def build_schema(
    dialect: str | type[dialects.Dialect],
    database: str,
    schema: str | None = None,
    table: str | None = None,
):
    resolved = (
        dialects.get_or_raise(dialect.lower()) if isinstance(dialect, str) else dialect
    )
    if resolved not in SUPPORTED_DIALECTS:
        raise ValueError(f"Unsupported dialect for build_schema: {resolved.__name__}")
    if resolved is dialects.BigQuery:
        return _build_schema_bigquery(database, schema, table)
    if resolved is dialects.Redshift:
        return _build_schema_redshift(database, schema, table)
    raise ValueError(f"Unsupported dialect for build_schema: {resolved.__name__}")


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


def _redshift_connection_kwargs(database: str) -> dict[str, str | int | bool]:
    host = os.getenv("REDSHIFT_HOST")
    port = os.getenv("REDSHIFT_PORT")

    cluster_identifier = os.getenv("REDSHIFT_CLUSTER_IDENTIFIER")
    region = os.getenv("REDSHIFT_REGION")
    db_user = os.getenv("REDSHIFT_DB_USER")

    user = os.getenv("REDSHIFT_USER")
    password = os.getenv("REDSHIFT_PASSWORD")

    if cluster_identifier and region and db_user:
        kwargs = {
            "cluster_identifier": cluster_identifier,
            "database": database,
            "db_user": db_user,
            "region": region,
            "iam": True,
        }
        if host:
            kwargs["host"] = host
            if port:
                kwargs["port"] = int(port)
        return kwargs

    if host and user and password:
        return {
            "host": host,
            "port": int(port) if port else 5439,
            "database": database,
            "user": user,
            "password": password,
        }

    raise RuntimeError(
        "Redshift connection configuration not found. "
        "Set REDSHIFT_HOST/REDSHIFT_USER/REDSHIFT_PASSWORD or "
        "REDSHIFT_CLUSTER_IDENTIFIER/REDSHIFT_REGION/REDSHIFT_DB_USER."
    )


def _build_schema_redshift(database: str, schema: str | None, table: str | None):
    try:
        import redshift_connector
    except ImportError as e:
        raise RuntimeError(
            "Redshift support is not installed. "
            "Install with: pip install analytics-query-analyzer[redshift]"
        ) from e

    connection_kwargs = _redshift_connection_kwargs(database)
    conn = redshift_connector.connect(**connection_kwargs)
    try:
        cursor = conn.cursor()
        try:
            if schema is None:
                cursor.execute(
                    """
                    select schema_name
                    from information_schema.schemata
                    where schema_name not in ('information_schema', 'pg_catalog')
                    and schema_name not like 'pg_%'
                    order by schema_name
                    """
                )
                schemas = [row[0] for row in cursor.fetchall()]
            else:
                schemas = [schema]

            result: dict[str, dict] = {}
            for schema_name in schemas:
                if table is None:
                    cursor.execute(
                        """
                        select table_name
                        from information_schema.tables
                        where table_schema = %s
                        and table_type = 'BASE TABLE'
                        order by table_name
                        """,
                        (schema_name,),
                    )
                    tables = [row[0] for row in cursor.fetchall()]
                else:
                    tables = [table]
                if not tables:
                    result[schema_name] = {}
                    continue

                placeholders = ", ".join(["%s"] * len(tables))
                cursor.execute(
                    f"""
                    select table_name, column_name, data_type, udt_name
                    from information_schema.columns
                    where table_schema = %s
                    and table_name in ({placeholders})
                    order by table_name, ordinal_position
                    """,
                    (schema_name, *tables),
                )
                table_schema: dict[str, dict[str, str]] = {name: {} for name in tables}
                for table_name, column_name, data_type, udt_name in cursor.fetchall():
                    column_type = data_type or udt_name or "unknown"
                    table_schema.setdefault(table_name, {})[column_name] = column_type
                result[schema_name] = table_schema
        finally:
            cursor.close()
    finally:
        conn.close()
    return {database: result}
