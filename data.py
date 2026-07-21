from __future__ import annotations

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import boto3
import duckdb
import pandas as pd
import streamlit as st
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from openpyxl import Workbook


# =============================================================================
# AWS S3 DEFAULTS
# Deployment-specific values can be overridden in Streamlit Secrets.
# =============================================================================
DEFAULT_AWS_REGION = "us-east-1"
DEFAULT_S3_BUCKET = "composite-bridge-data-568788909451-us-east-1-an"
DEFAULT_S3_OBJECTS = {
    "accell": "accell.csv",
    "deflect": "deflect.csv",
    "envir": "envir.csv",
    "logo": "logo.png",
}


# =============================================================================
# DATA AND QUERY SETTINGS
# =============================================================================
TIME_ZONE = "America/New_York"
EXCEL_MAX_DATA_ROWS = 1_048_575
MAX_GRAPH_POINTS = 300_000
DUCKDB_MEMORY_LIMIT = "1700MB"
DUCKDB_THREADS = 2
EXPORT_RETENTION_SECONDS = 2 * 60 * 60


# =============================================================================
# LOCAL CACHE PATHS
# Streamlit Community Cloud storage is temporary, so the cache is rebuilt after
# a server restart. It is shared by every active portal session on one server.
# =============================================================================
PROJECT_DIRECTORY = Path(__file__).resolve().parent
CACHE_DIRECTORY = Path(
    os.environ.get(
        "DATA_PORTAL_CACHE_DIR",
        str(Path(tempfile.gettempdir()) / "composite_bridge_data_portal"),
    )
)
CSV_DIRECTORY = CACHE_DIRECTORY / "source_csv"
EXPORT_DIRECTORY = CACHE_DIRECTORY / "exports"
DUCKDB_TEMP_DIRECTORY = CACHE_DIRECTORY / "duckdb_temp"
DUCKDB_PATH = CACHE_DIRECTORY / "composite_bridge.duckdb"
METADATA_PATH = CACHE_DIRECTORY / "metadata.json"
MANIFEST_PATH = CACHE_DIRECTORY / "s3_manifest.json"
CACHED_LOGO_PATH = CACHE_DIRECTORY / "logo.png"


# =============================================================================
# THREAD SAFETY
# DuckDB connections are opened per operation. This lock prevents a database
# refresh from replacing the database while another session is querying it.
# =============================================================================
DATABASE_LOCK = threading.RLock()


# =============================================================================
# DATASET DEFINITIONS
# Preferred columns keep the portal controls consistent and prevent identifier
# columns from accidentally appearing as graph variables.
# =============================================================================
DATASET_DEFINITIONS = {
    "accell": {
        "display_name": "Acceleration",
        "preferred_columns": ["Device ID", "X", "Y", "Z", "Magnitude"],
    },
    "deflect": {
        "display_name": "Deflection",
        "preferred_columns": ["Deflection"],
    },
    "envir": {
        "display_name": "Environmental",
        "preferred_columns": [
            "Temp0",
            "Temp1",
            "Temp2",
            "Temp3",
            "Temp4",
            "Temp5",
            "Temp6",
            "Temp7",
            "Temperature",
            "Average Temp",
            "Humidity",
            "Count",
        ],
    },
}


# =============================================================================
# TYPE ALIASES
# =============================================================================
ProgressCallback = Callable[[str, float], None]


# =============================================================================
# CUSTOM APPLICATION ERROR
# =============================================================================
class PortalDataError(RuntimeError):
    """A user-facing data loading, querying, or export error."""


# =============================================================================
# GENERAL FILE AND SQL HELPERS
# =============================================================================
def ensure_cache_directories() -> None:
    """Create the temporary directories used by the portal."""
    for directory in (
        CACHE_DIRECTORY,
        CSV_DIRECTORY,
        EXPORT_DIRECTORY,
        DUCKDB_TEMP_DIRECTORY,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def quote_identifier(value: str) -> str:
    """Safely quote a DuckDB table or column identifier."""
    return '"' + str(value).replace('"', '""') + '"'


def sql_string(value: str | Path) -> str:
    """Safely quote a DuckDB string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def safe_table_name(value: str) -> str:
    """Convert a dataset name into a safe DuckDB table name."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value))
    if cleaned and cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned or "dataset"


def normalize_column_name(value: str) -> str:
    """Normalize column names for tolerant matching."""
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).lower()


def find_column(columns: list[str], target: str) -> str | None:
    """Find a column using capitalization- and punctuation-insensitive matching."""
    normalized_target = normalize_column_name(target)
    for column in columns:
        if normalize_column_name(column) == normalized_target:
            return column
    return None


def read_json_file(path: Path, default: Any) -> Any:
    """Read JSON safely and return a default if the file is absent or invalid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json_file(path: Path, value: Any) -> None:
    """Write JSON atomically so interrupted writes do not corrupt the cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def report_progress(
    callback: ProgressCallback | None,
    message: str,
    fraction: float,
) -> None:
    """Report bounded progress when the Home page supplies a callback."""
    if callback is not None:
        callback(message, min(1.0, max(0.0, float(fraction))))


# =============================================================================
# STREAMLIT SECRETS AND AWS CLIENT
# =============================================================================
def get_secret_section(section_name: str) -> dict[str, Any]:
    """Return one Streamlit Secrets section as a plain dictionary."""
    try:
        section = st.secrets.get(section_name, {})
    except (FileNotFoundError, KeyError):
        return {}

    try:
        return dict(section)
    except (TypeError, ValueError):
        return {}


def get_aws_secret_values() -> dict[str, str]:
    """Read AWS credentials from Streamlit Secrets or standard environment variables."""
    aws_secrets = get_secret_section("aws")

    access_key_id = str(
        aws_secrets.get("access_key_id")
        or os.environ.get("AWS_ACCESS_KEY_ID", "")
    ).strip()
    secret_access_key = str(
        aws_secrets.get("secret_access_key")
        or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    ).strip()
    session_token = str(
        aws_secrets.get("session_token")
        or os.environ.get("AWS_SESSION_TOKEN", "")
    ).strip()

    return {
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "session_token": session_token,
    }


def build_s3_key(object_key: str, prefix: str) -> str:
    """Apply an optional S3 prefix to an object key."""
    cleaned_key = str(object_key).strip().strip("/")
    cleaned_prefix = str(prefix).strip().strip("/")
    if cleaned_prefix and not cleaned_key.startswith(f"{cleaned_prefix}/"):
        return f"{cleaned_prefix}/{cleaned_key}"
    return cleaned_key


def get_s3_settings() -> dict[str, Any]:
    """Read S3 bucket, region, and object names from Streamlit Secrets."""
    aws_secrets = get_secret_section("aws")
    bucket_name = str(
        aws_secrets.get("bucket_name")
        or aws_secrets.get("bucket")
        or os.environ.get("S3_BUCKET_NAME", "")
        or os.environ.get("AWS_S3_BUCKET", "")
        or DEFAULT_S3_BUCKET
    ).strip()
    region = str(
        aws_secrets.get("region")
        or os.environ.get("AWS_REGION", "")
        or os.environ.get("AWS_DEFAULT_REGION", "")
        or DEFAULT_AWS_REGION
    ).strip()
    prefix = str(
        aws_secrets.get("prefix")
        or os.environ.get("S3_PREFIX", "")
    ).strip()

    objects = {
        object_name: build_s3_key(
            str(
                aws_secrets.get(f"{object_name}_key")
                or aws_secrets.get(f"{object_name}_object")
                or default_key
            ),
            prefix,
        )
        for object_name, default_key in DEFAULT_S3_OBJECTS.items()
    }

    if not bucket_name:
        raise PortalDataError(
            "The S3 bucket name is missing. Add aws.bucket_name to Streamlit Secrets."
        )
    if not region:
        raise PortalDataError(
            "The AWS region is missing. Add aws.region to Streamlit Secrets."
        )

    return {
        "bucket_name": bucket_name,
        "region": region,
        "objects": objects,
    }


def create_s3_client(region_name: str):
    """Create a retry-enabled S3 client without exposing credentials."""
    credentials = get_aws_secret_values()

    client_arguments: dict[str, Any] = {
        "service_name": "s3",
        "region_name": region_name,
        "config": Config(
            retries={"max_attempts": 5, "mode": "adaptive"},
            connect_timeout=20,
            read_timeout=120,
        ),
    }

    if credentials["access_key_id"] and credentials["secret_access_key"]:
        client_arguments["aws_access_key_id"] = credentials["access_key_id"]
        client_arguments["aws_secret_access_key"] = credentials["secret_access_key"]
        if credentials["session_token"]:
            client_arguments["aws_session_token"] = credentials["session_token"]

    return boto3.client(**client_arguments)


# =============================================================================
# S3 DOWNLOAD AND CACHE VALIDATION
# =============================================================================
def local_path_for_object(dataset_name: str) -> Path:
    """Return the local cache path for a configured S3 object."""
    if dataset_name == "logo":
        return CACHED_LOGO_PATH
    return CSV_DIRECTORY / Path(DEFAULT_S3_OBJECTS[dataset_name]).name


def normalized_head_metadata(head_response: dict[str, Any]) -> dict[str, Any]:
    """Keep only stable S3 metadata needed to detect object changes."""
    last_modified = head_response.get("LastModified")
    return {
        "etag": str(head_response.get("ETag", "")).strip('"'),
        "size": int(head_response.get("ContentLength", 0)),
        "last_modified": (
            last_modified.isoformat() if hasattr(last_modified, "isoformat") else ""
        ),
    }


def object_needs_download(
    local_path: Path,
    previous_metadata: dict[str, Any],
    current_metadata: dict[str, Any],
) -> bool:
    """Return True when an S3 object is absent locally or has changed remotely."""
    if not local_path.exists():
        return True
    if local_path.stat().st_size != int(current_metadata.get("size", -1)):
        return True
    return (
        previous_metadata.get("etag") != current_metadata.get("etag")
        or previous_metadata.get("size") != current_metadata.get("size")
    )


def download_s3_object(
    client,
    bucket_name: str,
    object_key: str,
    destination: Path,
) -> None:
    """Download one S3 object to disk using an atomic final rename."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(destination.suffix + ".download")
    temporary_path.unlink(missing_ok=True)

    try:
        client.download_file(
            bucket_name,
            object_key,
            str(temporary_path),
            Config=TransferConfig(use_threads=False),
        )
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


# =============================================================================
# DUCKDB BUILD AND METADATA DISCOVERY
# =============================================================================
def configure_duckdb(connection: duckdb.DuckDBPyConnection) -> None:
    """Apply conservative resource settings suitable for Community Cloud."""
    connection.execute(f"PRAGMA threads={int(DUCKDB_THREADS)}")
    connection.execute(f"PRAGMA memory_limit={sql_string(DUCKDB_MEMORY_LIMIT)}")
    connection.execute(
        f"PRAGMA temp_directory={sql_string(DUCKDB_TEMP_DIRECTORY)}"
    )


def build_duckdb_database(
    progress_callback: ProgressCallback | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a fresh DuckDB database from the three locally cached CSV files."""
    ensure_cache_directories()
    building_path = CACHE_DIRECTORY / "composite_bridge.building.duckdb"
    building_wal_path = Path(str(building_path) + ".wal")
    building_path.unlink(missing_ok=True)
    building_wal_path.unlink(missing_ok=True)

    metadata: dict[str, dict[str, Any]] = {}
    connection = duckdb.connect(str(building_path))

    try:
        configure_duckdb(connection)

        dataset_order = ["accell", "deflect", "envir"]
        for index, dataset_name in enumerate(dataset_order):
            csv_path = local_path_for_object(dataset_name)
            if not csv_path.exists() or csv_path.stat().st_size == 0:
                raise PortalDataError(f"{csv_path.name} is missing or empty.")

            report_progress(
                progress_callback,
                f"Importing {csv_path.name} into DuckDB...",
                0.55 + (index / len(dataset_order)) * 0.35,
            )

            table_name = safe_table_name(dataset_name)
            connection.execute(
                f"""
                CREATE OR REPLACE TABLE {quote_identifier(table_name)} AS
                SELECT *
                FROM read_csv_auto(
                    {sql_string(csv_path)},
                    header = true,
                    sample_size = 1000000,
                    ignore_errors = true,
                    null_padding = true
                )
                """
            )

            description = connection.execute(
                f"DESCRIBE {quote_identifier(table_name)}"
            ).fetchdf()
            columns = [str(value).strip() for value in description["column_name"].tolist()]
            time_column = find_column(columns, "time")
            if time_column is None:
                raise PortalDataError(f"{csv_path.name} does not contain a time column.")

            preferred_columns = DATASET_DEFINITIONS[dataset_name]["preferred_columns"]
            available_columns = [
                matched
                for preferred in preferred_columns
                if (matched := find_column(columns, preferred)) is not None
            ]

            summary = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS row_count,
                    MIN(TRY_CAST({quote_identifier(time_column)} AS DOUBLE)) AS start_unix,
                    MAX(TRY_CAST({quote_identifier(time_column)} AS DOUBLE)) AS end_unix
                FROM {quote_identifier(table_name)}
                WHERE TRY_CAST({quote_identifier(time_column)} AS DOUBLE) IS NOT NULL
                """
            ).fetchone()

            if summary is None or summary[1] is None or summary[2] is None:
                raise PortalDataError(f"{csv_path.name} has no usable time values.")

            try:
                connection.execute(
                    f"""
                    CREATE INDEX {quote_identifier(table_name + '_time_index')}
                    ON {quote_identifier(table_name)} ({quote_identifier(time_column)})
                    """
                )
            except Exception:
                # Queries remain valid if DuckDB decides an index is not useful.
                pass

            metadata[dataset_name] = {
                "name": dataset_name,
                "display_name": DATASET_DEFINITIONS[dataset_name]["display_name"],
                "table": table_name,
                "time_col": time_column,
                "columns": columns,
                "numeric_cols": available_columns,
                "row_count": int(summary[0]),
                "start_unix": float(summary[1]),
                "end_unix": float(summary[2]),
                "source_file": csv_path.name,
            }

        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    with DATABASE_LOCK:
        DUCKDB_PATH.unlink(missing_ok=True)
        Path(str(DUCKDB_PATH) + ".wal").unlink(missing_ok=True)
        os.replace(building_path, DUCKDB_PATH)

    return metadata


# =============================================================================
# PUBLIC DATA LOADING FUNCTION USED BY THE HOME PAGE
# =============================================================================
def initialize_database(
    progress_callback: ProgressCallback | None = None,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Download changed S3 objects and create or reuse the DuckDB database.

    Returns:
        A tuple containing dataset metadata and a Boolean that is True when the
        DuckDB database was rebuilt during this call.
    """
    ensure_cache_directories()
    report_progress(progress_callback, "Connecting securely to Amazon S3...", 0.02)

    try:
        s3_settings = get_s3_settings()
        bucket_name = s3_settings["bucket_name"]
        region = s3_settings["region"]
        s3_objects = s3_settings["objects"]
        client = create_s3_client(region)
        previous_manifest = read_json_file(MANIFEST_PATH, {"objects": {}})
        manifest_context_changed = (
            previous_manifest.get("bucket") != bucket_name
            or previous_manifest.get("region") != region
        )
        current_manifest: dict[str, Any] = {
            "bucket": bucket_name,
            "region": region,
            "objects": {},
        }
        changed_csv = False

        object_order = ["logo", "accell", "deflect", "envir"]
        for index, object_name in enumerate(object_order):
            object_key = s3_objects[object_name]
            report_progress(
                progress_callback,
                f"Checking {object_key}...",
                0.04 + index * 0.08,
            )

            head_response = client.head_object(Bucket=bucket_name, Key=object_key)
            remote_metadata = normalized_head_metadata(head_response)
            current_manifest["objects"][object_name] = remote_metadata
            local_path = local_path_for_object(object_name)
            previous_metadata = previous_manifest.get("objects", {}).get(object_name, {})

            if manifest_context_changed or object_needs_download(
                local_path,
                previous_metadata,
                remote_metadata,
            ):
                report_progress(
                    progress_callback,
                    f"Downloading {object_key} from S3...",
                    0.08 + index * 0.10,
                )
                download_s3_object(client, bucket_name, object_key, local_path)
                if object_name != "logo":
                    changed_csv = True

        existing_metadata = get_metadata()
        database_rebuilt = changed_csv or not DUCKDB_PATH.exists() or not existing_metadata

        if database_rebuilt:
            metadata = build_duckdb_database(progress_callback)
        else:
            metadata = existing_metadata
            report_progress(
                progress_callback,
                "S3 files are unchanged; reusing the existing DuckDB database.",
                0.88,
            )

        loaded_at = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %I:%M:%S %p %Z")
        metadata_document = {
            "loaded_at": loaded_at,
            "bucket": bucket_name,
            "region": region,
            "datasets": metadata,
        }
        current_manifest["loaded_at"] = loaded_at
        write_json_file(METADATA_PATH, metadata_document)
        write_json_file(MANIFEST_PATH, current_manifest)
        report_progress(progress_callback, "Composite Bridge data is ready.", 1.0)
        return metadata, database_rebuilt

    except PortalDataError:
        raise
    except Exception as exc:
        raise PortalDataError(
            "The portal could not load the S3 data. Confirm the AWS credentials, "
            "bucket permissions, region, and object names. "
            f"Technical detail: {exc}"
        ) from exc


# =============================================================================
# DATABASE STATUS AND METADATA ACCESS
# =============================================================================
def get_metadata() -> dict[str, dict[str, Any]]:
    """Return cached dataset metadata, or an empty mapping if data is unavailable."""
    document = read_json_file(METADATA_PATH, {})
    datasets = document.get("datasets", {}) if isinstance(document, dict) else {}
    return datasets if isinstance(datasets, dict) else {}


def get_database_summary() -> dict[str, Any]:
    """Return non-sensitive information about the current local database."""
    document = read_json_file(METADATA_PATH, {})
    if not isinstance(document, dict):
        return {}
    return {
        "loaded_at": document.get("loaded_at"),
        "bucket": document.get("bucket"),
        "region": document.get("region"),
        "datasets": document.get("datasets", {}),
    }


def database_ready() -> bool:
    """Return True when both DuckDB and usable dataset metadata exist."""
    return DUCKDB_PATH.exists() and bool(get_metadata())


def get_logo_path(fallback_path: Path | None = None) -> Path | None:
    """Return the latest downloaded logo, with a bundled fallback for first use."""
    if CACHED_LOGO_PATH.exists() and CACHED_LOGO_PATH.stat().st_size > 0:
        return CACHED_LOGO_PATH
    if fallback_path is not None and fallback_path.exists():
        return fallback_path
    return None


def connect_duckdb() -> duckdb.DuckDBPyConnection:
    """Open a read-only connection to the loaded DuckDB database."""
    if not database_ready():
        raise PortalDataError("Press Load Data on the Home page before continuing.")
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


def overall_time_bounds(metadata: dict[str, dict[str, Any]]) -> tuple[float, float]:
    """Return the earliest and latest Unix timestamps across all datasets."""
    if not metadata:
        raise PortalDataError("No bridge data is loaded.")
    return (
        min(float(item["start_unix"]) for item in metadata.values()),
        max(float(item["end_unix"]) for item in metadata.values()),
    )


# =============================================================================
# VARIABLE GROUPS AND SERIES SPECIFICATIONS
# =============================================================================
def get_variable_groups(metadata: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe the variable groups displayed on graphing and export pages."""
    groups: list[dict[str, Any]] = []
    dataset_order = [name for name in ("accell", "deflect", "envir") if name in metadata]
    dataset_order.extend(name for name in metadata if name not in dataset_order)

    for dataset_name in dataset_order:
        item = metadata[dataset_name]
        columns = list(item.get("numeric_cols", []))
        device_column = find_column(columns, "Device ID")
        acceleration_variables = [
            matched
            for target in ("X", "Y", "Z", "Magnitude")
            if (matched := find_column(columns, target)) is not None
        ]

        if dataset_name == "accell" and device_column and acceleration_variables:
            groups.extend(
                [
                    {
                        "key": "accell_device_1",
                        "label": "Acceleration Device 1",
                        "dataset": dataset_name,
                        "variables": acceleration_variables,
                        "filter_column": device_column,
                        "filter_value": 0,
                    },
                    {
                        "key": "accell_device_2",
                        "label": "Acceleration Device 2",
                        "dataset": dataset_name,
                        "variables": acceleration_variables,
                        "filter_column": device_column,
                        "filter_value": 1,
                    },
                ]
            )
        else:
            selectable_columns = [
                column for column in columns if normalize_column_name(column) != "deviceid"
            ]
            groups.append(
                {
                    "key": f"{dataset_name}_all",
                    "label": str(item.get("display_name", dataset_name.title())),
                    "dataset": dataset_name,
                    "variables": selectable_columns,
                    "filter_column": None,
                    "filter_value": None,
                }
            )

    return groups


def build_series_specs(
    metadata: dict[str, dict[str, Any]],
    selections: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Convert page selections into validated graph/export query specifications."""
    specs: list[dict[str, Any]] = []
    used_export_names: set[str] = set()

    for group in get_variable_groups(metadata):
        item = metadata[group["dataset"]]
        allowed = set(group["variables"])
        selected_variables = [
            variable for variable in selections.get(group["key"], []) if variable in allowed
        ]

        for variable in selected_variables:
            if group["filter_column"] is not None:
                export_name = f"{group['label']}_{variable}"
            else:
                export_name = variable

            if export_name in used_export_names:
                export_name = f"{item['display_name']}_{export_name}"
            used_export_names.add(export_name)

            specs.append(
                {
                    "dataset": group["dataset"],
                    "table": item["table"],
                    "time_col": item["time_col"],
                    "variable": variable,
                    "series_label": f"{group['label']}: {variable}",
                    "export_name": export_name,
                    "filter_column": group["filter_column"],
                    "filter_value": group["filter_value"],
                }
            )

    return specs


# =============================================================================
# DUCKDB SERIES QUERY BUILDING
# =============================================================================
def numeric_filter_sql(spec: dict[str, Any]) -> str:
    """Return the optional numeric Device ID filter for one series."""
    column = spec.get("filter_column")
    value = spec.get("filter_value")
    if column is None or value is None:
        return ""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise PortalDataError("A device filter value is invalid.") from exc
    return (
        f" AND TRY_CAST({quote_identifier(column)} AS DOUBLE) = "
        f"{format(numeric_value, '.15g')}"
    )


def build_single_series_query(
    spec: dict[str, Any],
    start_unix: float,
    end_unix: float,
    frequency_seconds: float,
) -> str:
    """Build a safe DuckDB query for one selected variable."""
    filter_sql = numeric_filter_sql(spec)
    start_value = format(float(start_unix), ".17g")
    end_value = format(float(end_unix), ".17g")

    base_query = f"""
        SELECT
            TRY_CAST({quote_identifier(spec['time_col'])} AS DOUBLE) AS time_num,
            TRY_CAST({quote_identifier(spec['variable'])} AS DOUBLE) AS value_num
        FROM {quote_identifier(spec['table'])}
        WHERE TRY_CAST({quote_identifier(spec['time_col'])} AS DOUBLE)
              BETWEEN {start_value} AND {end_value}
          AND TRY_CAST({quote_identifier(spec['variable'])} AS DOUBLE) IS NOT NULL
          {filter_sql}
    """

    if float(frequency_seconds) > 0:
        frequency_value = format(float(frequency_seconds), ".17g")
        return f"""
            SELECT time_num, value_num
            FROM (
                SELECT
                    time_num,
                    value_num,
                    ROW_NUMBER() OVER (
                        PARTITION BY FLOOR(time_num / {frequency_value})
                        ORDER BY time_num
                    ) AS selected_row
                FROM ({base_query}) AS filtered
            ) AS bucketed
            WHERE selected_row = 1
        """

    # One output value per exact timestamp keeps multi-dataset exports stable.
    return f"""
        SELECT time_num, FIRST(value_num) AS value_num
        FROM ({base_query}) AS filtered
        GROUP BY time_num
    """


# =============================================================================
# GRAPH DATA QUERY
# =============================================================================
def query_graph_data(
    specs: list[dict[str, Any]],
    start_unix: float,
    end_unix: float,
    frequency_seconds: float,
) -> pd.DataFrame:
    """Query selected graph series while enforcing a browser-safe point limit."""
    if not specs:
        raise PortalDataError("Select at least one variable to graph.")

    frames: list[pd.DataFrame] = []
    remaining_points = MAX_GRAPH_POINTS

    with DATABASE_LOCK:
        connection = connect_duckdb()
        try:
            configure_duckdb(connection)
            for spec in specs:
                series_query = build_single_series_query(
                    spec,
                    start_unix,
                    end_unix,
                    frequency_seconds,
                )
                result = connection.execute(
                    f"""
                    SELECT time_num, value_num
                    FROM ({series_query}) AS selected_series
                    ORDER BY time_num
                    LIMIT {int(remaining_points + 1)}
                    """
                ).fetchdf()

                if len(result) > remaining_points:
                    raise PortalDataError(
                        f"Plot exceeds the {MAX_GRAPH_POINTS:,} row limit. "
                        "Increase the minimum point interval or shorten the time range."
                    )

                remaining_points -= len(result)
                if result.empty:
                    continue

                frame = pd.DataFrame(
                    {
                        "DateTime": pd.to_datetime(
                            result["time_num"], unit="s", utc=True
                        ).dt.tz_convert(TIME_ZONE),
                        "Value": pd.to_numeric(result["value_num"], errors="coerce"),
                        "Series": spec["series_label"],
                    }
                ).dropna(subset=["DateTime", "Value"])
                if not frame.empty:
                    frames.append(frame)
        finally:
            connection.close()

    if not frames:
        return pd.DataFrame(columns=["DateTime", "Value", "Series"])
    return pd.concat(frames, ignore_index=True).sort_values(["Series", "DateTime"])


# =============================================================================
# COMBINED EXPORT QUERY
# Each series retains its own timestamps. UNION creates the complete time axis,
# and LEFT JOINs place every selected variable into one output table.
# =============================================================================
def build_export_query(
    specs: list[dict[str, Any]],
    start_unix: float,
    end_unix: float,
    frequency_seconds: float,
) -> tuple[str, str]:
    """Return the full export query and the exact distinct-time row-count query."""
    if not specs:
        raise PortalDataError("Select at least one variable to export.")

    cte_parts: list[str] = []
    time_parts: list[str] = []
    join_parts: list[str] = []
    select_parts: list[str] = [
        f"to_timestamp(all_times.time_num) AT TIME ZONE {sql_string(TIME_ZONE)} AS Date"
    ]

    for index, spec in enumerate(specs):
        cte_name = f"series_{index}"
        series_query = build_single_series_query(
            spec,
            start_unix,
            end_unix,
            frequency_seconds,
        )
        cte_parts.append(f"{cte_name} AS ({series_query})")
        time_parts.append(f"SELECT time_num FROM {cte_name}")
        join_parts.append(f"LEFT JOIN {cte_name} USING (time_num)")
        select_parts.append(
            f"{cte_name}.value_num AS {quote_identifier(spec['export_name'])}"
        )

    cte_sql = ",\n".join(cte_parts)
    all_times_sql = "\nUNION\n".join(time_parts)
    joins_sql = "\n".join(join_parts)
    selected_columns_sql = ",\n".join(select_parts)

    export_query = f"""
        WITH
        {cte_sql},
        all_times AS (
            {all_times_sql}
        )
        SELECT
            {selected_columns_sql}
        FROM all_times
        {joins_sql}
        ORDER BY all_times.time_num
    """

    count_query = f"""
        WITH
        {cte_sql},
        all_times AS (
            {all_times_sql}
        )
        SELECT COUNT(*)
        FROM all_times
    """
    return export_query, count_query


def count_export_rows(
    specs: list[dict[str, Any]],
    start_unix: float,
    end_unix: float,
    frequency_seconds: float,
) -> int:
    """Count the exact number of rows in the combined export."""
    _, count_query = build_export_query(
        specs,
        start_unix,
        end_unix,
        frequency_seconds,
    )
    with DATABASE_LOCK:
        connection = connect_duckdb()
        try:
            configure_duckdb(connection)
            result = connection.execute(count_query).fetchone()
        finally:
            connection.close()
    return int(result[0]) if result else 0


# =============================================================================
# CSV AND EXCEL FILE GENERATION
# =============================================================================
def clean_old_exports() -> None:
    """Remove temporary exports after two hours to conserve server storage."""
    ensure_cache_directories()
    cutoff = time.time() - EXPORT_RETENTION_SECONDS
    for path in EXPORT_DIRECTORY.glob("BridgeData_*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def create_export_file(
    specs: list[dict[str, Any]],
    start_unix: float,
    end_unix: float,
    frequency_seconds: float,
    file_format: str,
) -> tuple[Path, int]:
    """Create one CSV or one Excel workbook containing all selected variables."""
    normalized_format = str(file_format).strip().lower()
    if normalized_format not in {"csv", "excel"}:
        raise PortalDataError("Choose CSV or Excel as the export format.")

    clean_old_exports()
    export_query, count_query = build_export_query(
        specs,
        start_unix,
        end_unix,
        frequency_seconds,
    )

    timestamp = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d_%H-%M-%S")
    suffix = ".csv" if normalized_format == "csv" else ".xlsx"
    output_path = EXPORT_DIRECTORY / f"BridgeData_{timestamp}{suffix}"

    with DATABASE_LOCK:
        connection = connect_duckdb()
        try:
            configure_duckdb(connection)
            count_result = connection.execute(count_query).fetchone()
            row_count = int(count_result[0]) if count_result else 0
            if row_count == 0:
                raise PortalDataError("No selected variables contain data in this time range.")

            if normalized_format == "excel" and row_count > EXCEL_MAX_DATA_ROWS:
                raise PortalDataError("Data set is too large for an Excel file.")

            if normalized_format == "csv":
                connection.execute(
                    f"""
                    COPY ({export_query})
                    TO {sql_string(output_path)}
                    (FORMAT CSV, HEADER TRUE, DELIMITER ',')
                    """
                )
            else:
                workbook = Workbook(write_only=True)
                worksheet = workbook.create_sheet(title="Bridge Data")
                cursor = connection.execute(export_query)
                headers = [description[0] for description in cursor.description]
                worksheet.append(headers)

                while True:
                    rows = cursor.fetchmany(10_000)
                    if not rows:
                        break
                    for row in rows:
                        worksheet.append(list(row))

                workbook.save(output_path)
        except Exception:
            output_path.unlink(missing_ok=True)
            raise
        finally:
            connection.close()

    return output_path, row_count


# =============================================================================
# DISPLAY HELPERS USED BY MULTIPLE PAGES
# =============================================================================
def format_unix_time(unix_value: float) -> str:
    """Format a Unix timestamp in Eastern Time for portal status displays."""
    return datetime.fromtimestamp(float(unix_value), ZoneInfo(TIME_ZONE)).strftime(
        "%Y-%m-%d %I:%M:%S %p %Z"
    )


def human_file_size(size_bytes: int) -> str:
    """Format a byte count for an export download message."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"
