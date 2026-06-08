from __future__ import annotations

import subprocess
import sys

subprocess.check_call([sys.executable, "-m", "pip", "install",
    "requests", "pandas", "sqlalchemy", "psycopg2-binary"])

"""
Cincinnati Weather Trend and Severe Weather Monitoring Dashboard
================================================================
Week 3 ETL Pipeline — Transformation & Data Quality Engineering

This script implements a complete, reproducible ETL pipeline that:
  - Extracts daily weather forecast data from the Open-Meteo API
  - Cleans, normalizes, and transforms the raw response
  - Applies derived metrics and severe weather alert logic
  - Validates data quality at multiple checkpoints
  - Loads processed data into PostgreSQL using an incremental upsert strategy
  - Saves a finalized CSV dataset for Power BI analytics

Location : Cincinnati, OH (39.1271N, 84.5144W)
API      : Open-Meteo (https://open-meteo.com/) — free, no API key required
Database : PostgreSQL (EDB)
"""


from pathlib import Path
from datetime import datetime

import logging
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.types import Boolean, Date, Float, Integer, Numeric, SmallInteger, String


# ---------------------------------------------------------------------------
# DATABASE CONFIGURATION
# Update these values before running
# ---------------------------------------------------------------------------

DB_HOST     = "localhost"
DB_PORT     = 5432
DB_NAME     = "Logan"
DB_USER     = "postgres"
DB_PASSWORD = "Incorrect11*"


# ---------------------------------------------------------------------------
# PIPELINE CONFIGURATION
# Keep all source parameters and file paths in one place so the pipeline
# is easy to rerun or hand off to another engineer.
# ---------------------------------------------------------------------------

BASE_URL      = "https://api.open-meteo.com/v1/forecast"
OUTPUT_PATH   = Path("cincinnati_weather.csv")

PARAMS = {
    "latitude":           39.1271,
    "longitude":         -84.5144,
    "timezone":           "America/New_York",
    "forecast_days":      16,
    "temperature_unit":   "fahrenheit",
    "wind_speed_unit":    "mph",
    "precipitation_unit": "inch",
    "daily": [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "precipitation_probability_max",
        "weathercode",
    ],
}

# Severe weather alert thresholds
THRESHOLDS = {
    "freeze_temp_f":        32.0,
    "heat_temp_f":          90.0,
    "extreme_heat_temp_f": 100.0,
    "heavy_precip_in":       1.5,
    "extreme_precip_in":     3.0,
    "high_wind_mph":        35.0,
    "extreme_wind_mph":     60.0,
}

# WMO weather code lookup
WMO_CODES = {
    0:  "Clear Sky",
    1:  "Mainly Clear",    2: "Partly Cloudy",         3: "Overcast",
    45: "Foggy",          48: "Icy Fog",
    51: "Light Drizzle",  53: "Moderate Drizzle",      55: "Dense Drizzle",
    61: "Slight Rain",    63: "Moderate Rain",          65: "Heavy Rain",
    71: "Slight Snow",    73: "Moderate Snow",          75: "Heavy Snow",
    77: "Snow Grains",
    80: "Slight Rain Showers", 81: "Moderate Rain Showers", 82: "Violent Rain Showers",
    85: "Slight Snow Showers", 86: "Heavy Snow Showers",
    95: "Thunderstorm",   96: "Thunderstorm w/ Slight Hail", 99: "Thunderstorm w/ Heavy Hail",
}


# ---------------------------------------------------------------------------
# LOGGING SETUP
# Logging is better than print statements because logs are timestamped,
# filterable, and can be captured by schedulers or orchestration tools.
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# STEP 1: EXTRACTION
# Retrieve raw forecast data from the Open-Meteo API.
# ---------------------------------------------------------------------------

def extract_weather_data() -> dict:
    """
    Fetch daily weather forecast data from the Open-Meteo API.
    Returns the raw JSON response as a Python dictionary.
    """
    logger.info("Extracting weather forecast from Open-Meteo API...")

    try:
        response = requests.get(BASE_URL, params=PARAMS, timeout=30)
        response.raise_for_status()
        data = response.json()
        logger.info("Successfully retrieved %s days of forecast data.", len(data["daily"]["time"]))
        return data

    except requests.exceptions.ConnectionError:
        # Error handling example:
        # Each exception type gets a specific, actionable error message instead
        # of a generic failure, making debugging faster.
        logger.exception("Connection failed. Check your internet connection.")
        raise
    except requests.exceptions.Timeout:
        logger.exception("Request timed out. The API may be slow — try again.")
        raise
    except requests.exceptions.HTTPError as e:
        logger.exception("HTTP error from API: %s", e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during extraction: %s", e)
        raise


# ---------------------------------------------------------------------------
# STEP 2: API RESPONSE VALIDATION
# Validate the raw response before transformation. Catching source contract
# changes early gives a clear failure point instead of silent bad data.
# ---------------------------------------------------------------------------

def validate_raw_response(raw: dict) -> None:
    """
    Validate that the API response contains the minimum required structure.
    Raises ValueError with a descriptive message if validation fails.
    """
    # Data validation check: confirm response is a dictionary
    if not isinstance(raw, dict):
        raise ValueError("API response must be a dictionary.")

    # Data validation check: confirm daily block exists
    daily = raw.get("daily")
    if not daily:
        raise ValueError(f"No daily data in API response. Raw: {raw}")

    # Data validation check: confirm required fields are present
    required_fields = {
        "time", "weathercode", "temperature_2m_max", "temperature_2m_min",
        "precipitation_sum", "wind_speed_10m_max", "wind_gusts_10m_max",
        "precipitation_probability_max",
    }
    missing = required_fields.difference(daily.keys())
    if missing:
        raise ValueError(f"API response missing required fields: {sorted(missing)}")

    # API response validation: confirm expected row count was returned
    actual_days = len(daily["time"])
    if actual_days < 1:
        raise ValueError("API returned zero forecast days.")
    if actual_days < PARAMS["forecast_days"]:
        logger.warning(
            "Expected %s forecast days but received %s.",
            PARAMS["forecast_days"], actual_days
        )

    logger.info("Raw API response validation passed.")


# ---------------------------------------------------------------------------
# STEP 3: CLEANING AND NORMALIZATION
# Rename columns to a consistent standard, enforce numeric types, and
# fill known-safe defaults for missing values.
# ---------------------------------------------------------------------------

def clean_and_normalize(raw: dict) -> pd.DataFrame:
    """
    Build a clean, normalized DataFrame from the raw API response.
    Renames columns, converts types, and fills safe defaults.
    """
    logger.info("Cleaning and normalizing forecast data...")

    daily = raw["daily"]

    df = pd.DataFrame({
        "date":                  daily["time"],
        "weather_code":          daily["weathercode"],
        "temp_max_f":            daily["temperature_2m_max"],
        "temp_min_f":            daily["temperature_2m_min"],
        "precip_inches":         daily["precipitation_sum"],
        "wind_speed_max_mph":    daily["wind_speed_10m_max"],
        "wind_gusts_max_mph":    daily["wind_gusts_10m_max"],
        "precip_probability_pct": daily["precipitation_probability_max"],
    })

    # Cleaning example:
    # Convert date string to datetime. A proper datetime type prevents silent
    # string-sort errors and enables date arithmetic downstream.
    df["date"] = pd.to_datetime(df["date"])

    # Cleaning example:
    # Enforce numeric types after extraction. errors="coerce" turns malformed
    # values into NaN so validation catches them instead of letting bad strings
    # leak into calculations.
    numeric_cols = [
        "weather_code", "temp_max_f", "temp_min_f",
        "precip_inches", "wind_speed_max_mph", "wind_gusts_max_mph",
        "precip_probability_pct",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Cleaning example:
    # Fill precipitation NaN with 0 — missing precipitation data from the API
    # means no measurable precipitation was recorded, not truly missing data.
    df["precip_inches"] = df["precip_inches"].fillna(0)

    logger.info("Cleaned %s rows.", len(df))
    return df


# ---------------------------------------------------------------------------
# STEP 4: TRANSFORMATION AND DERIVED METRICS
# Create fields that are easier for analysts to consume than raw source values.
# Derived metrics belong in ETL because they are deterministic and reusable.
# ---------------------------------------------------------------------------

def transform_and_derive_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived metrics, weather descriptions, calendar fields,
    and severe weather alert logic to the cleaned DataFrame.
    """
    logger.info("Applying transformations and derived metrics...")

    # Derived metrics example:
    # Temperature range and average give analysts instant context without
    # requiring them to calculate it themselves in every report.
    df["temp_range_f"] = df["temp_max_f"] - df["temp_min_f"]
    df["temp_avg_f"]   = ((df["temp_max_f"] + df["temp_min_f"]) / 2).round(1)

    # Derived metric: boolean precipitation flag for easy filtering
    df["has_precipitation"] = df["precip_inches"] > 0

    # Derived metric: human-readable weather description from WMO code
    df["weather_description"] = df["weather_code"].map(WMO_CODES).fillna("Unknown")

    # Derived metrics: calendar fields useful for Power BI slicers and filters
    df["day_of_week"]  = df["date"].dt.day_name()
    df["month"]        = df["date"].dt.month_name()
    df["week_number"]  = df["date"].dt.isocalendar().week.astype(int)

    # Derived metrics: severe weather alert logic
    # Each alert type is evaluated independently so multiple alerts can fire
    # on the same day (e.g. a freeze alert and a high wind alert together).
    df = df.apply(_apply_alert_logic, axis=1)

    # Metadata: track when the pipeline ran for audit and debugging purposes
    df["pipeline_run_date"] = datetime.now().strftime("%Y-%m-%d")
    df["pipeline_run_time"] = datetime.now().strftime("%H:%M:%S")
    df["data_source"]       = "Open-Meteo API"
    df["location"]          = "Cincinnati, OH"

    logger.info("Transformation complete. %s rows, %s columns.", len(df), len(df.columns))
    return df


def _apply_alert_logic(row: pd.Series) -> pd.Series:
    """
    Evaluate severe weather thresholds for a single forecast row.
    Adds alert flag columns and an overall severe_weather_day indicator.
    """
    t = THRESHOLDS

    # Temperature alerts
    row["freeze_alert"]     = row["temp_min_f"] <= t["freeze_temp_f"]
    row["alert_freeze_lvl"] = "Freeze" if row["freeze_alert"] else "None"

    if row["temp_max_f"] >= t["extreme_heat_temp_f"]:
        row["heat_alert"]     = True
        row["alert_heat_lvl"] = "Extreme Heat"
    elif row["temp_max_f"] >= t["heat_temp_f"]:
        row["heat_alert"]     = True
        row["alert_heat_lvl"] = "Heat"
    else:
        row["heat_alert"]     = False
        row["alert_heat_lvl"] = "None"

    # Precipitation alerts
    if row["precip_inches"] >= t["extreme_precip_in"]:
        row["precip_alert"]     = True
        row["alert_precip_lvl"] = "Extreme Precipitation"
    elif row["precip_inches"] >= t["heavy_precip_in"]:
        row["precip_alert"]     = True
        row["alert_precip_lvl"] = "Heavy Precipitation"
    else:
        row["precip_alert"]     = False
        row["alert_precip_lvl"] = "None"

    # Wind alerts
    if row["wind_speed_max_mph"] >= t["extreme_wind_mph"]:
        row["wind_alert"]      = True
        row["alert_wind_lvl"]  = "Extreme Wind"
    elif row["wind_speed_max_mph"] >= t["high_wind_mph"]:
        row["wind_alert"]      = True
        row["alert_wind_lvl"]  = "High Wind"
    else:
        row["wind_alert"]      = False
        row["alert_wind_lvl"]  = "None"

    # Overall flag and count
    row["severe_weather_day"] = any([
        row["freeze_alert"], row["heat_alert"],
        row["precip_alert"], row["wind_alert"],
    ])
    row["alert_count"] = sum([
        row["freeze_alert"], row["heat_alert"],
        row["precip_alert"], row["wind_alert"],
    ])

    return row


# ---------------------------------------------------------------------------
# STEP 5: DATA VALIDATION AND QUALITY CHECKS
# Run quality checks after transformation. Validation logic should include
# informative log messages indicating success or failure at each check.
# ---------------------------------------------------------------------------

def validate_clean_forecast(df: pd.DataFrame) -> None:
    """
    Run data quality checks on the transformed DataFrame.
    Raises ValueError with a descriptive message if any check fails.
    """
    logger.info("Running data quality checks...")

    # Schema validation: confirm all expected columns are present
    required_cols = {
        "date", "weather_code", "temp_max_f", "temp_min_f", "temp_avg_f",
        "temp_range_f", "precip_inches", "precip_probability_pct",
        "wind_speed_max_mph", "wind_gusts_max_mph", "weather_description",
        "severe_weather_day", "alert_count",
    }
    missing_cols = required_cols.difference(df.columns)
    if missing_cols:
        raise ValueError(f"Schema validation failed — missing columns: {sorted(missing_cols)}")
    logger.info("  Schema validation passed.")

    # Null value check: critical analytical fields must not be null
    required_non_null = ["date", "temp_max_f", "temp_min_f", "weather_code"]
    null_counts = df[required_non_null].isna().sum()
    if null_counts.any():
        raise ValueError(f"Null value check failed: {null_counts[null_counts > 0].to_dict()}")
    logger.info("  Null value check passed.")

    # Duplicate detection: each forecast date must appear exactly once
    duplicate_dates = df[df["date"].duplicated()]["date"].tolist()
    if duplicate_dates:
        raise ValueError(f"Duplicate detection failed — duplicate dates: {duplicate_dates}")
    logger.info("  Duplicate detection passed.")

    # Range validation: max temp must be greater than or equal to min temp
    invalid_temps = df[df["temp_max_f"] < df["temp_min_f"]]
    if not invalid_temps.empty:
        raise ValueError(
            f"Range validation failed — {len(invalid_temps)} rows where temp_max < temp_min."
        )
    logger.info("  Temperature range validation passed.")

    # Range validation: precipitation probability must be between 0 and 100
    invalid_prob = df[~df["precip_probability_pct"].between(0, 100)]
    if not invalid_prob.empty:
        raise ValueError(
            f"Range validation failed — precipitation probability outside 0-100%: "
            f"{invalid_prob['precip_probability_pct'].tolist()}"
        )
    logger.info("  Precipitation probability range validation passed.")

    # Range validation: precipitation and wind must be non-negative
    if (df["precip_inches"] < 0).any():
        raise ValueError("Range validation failed — negative precipitation values found.")
    if (df["wind_speed_max_mph"] < 0).any():
        raise ValueError("Range validation failed — negative wind speed values found.")
    logger.info("  Precipitation and wind range validation passed.")

    # Datatype validation: weather_code must be integer-compatible
    if not pd.api.types.is_numeric_dtype(df["weather_code"]):
        raise ValueError("Datatype validation failed — weather_code must be numeric.")
    logger.info("  Datatype validation passed.")

    # Row count verification: confirm expected number of rows loaded
    logger.info("  Row count verification: %s rows passed all checks.", len(df))

    logger.info("All data quality checks passed.")


# ---------------------------------------------------------------------------
# STEP 6: WEEKLY AGGREGATION LAYER
# Build a weekly summary for use as an additional analytics-ready dataset.
# Aggregation layers reduce the work analysts need to do in Power BI.
# ---------------------------------------------------------------------------

def build_weekly_aggregation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate daily forecast data into a weekly summary layer.
    Includes average temperatures, total precipitation, and severe weather counts.
    """
    logger.info("Building weekly aggregation layer...")

    weekly_df = df.set_index("date").copy()
    weekly_df.index = pd.to_datetime(weekly_df.index)

    weekly_df = weekly_df.resample("W").agg(
        avg_temp_f               = ("temp_avg_f",          "mean"),
        max_temp_f               = ("temp_max_f",           "max"),
        min_temp_f               = ("temp_min_f",           "min"),
        total_precip_inches      = ("precip_inches",        "sum"),
        rainy_days               = ("has_precipitation",    "sum"),
        severe_weather_days      = ("severe_weather_day",   "sum"),
        avg_wind_speed_mph       = ("wind_speed_max_mph",   "mean"),
        max_wind_speed_mph       = ("wind_speed_max_mph",   "max"),
    ).round({"avg_temp_f": 1, "max_temp_f": 1, "min_temp_f": 1,
             "total_precip_inches": 2, "avg_wind_speed_mph": 1})

    logger.info("Weekly aggregation complete. %s weeks.", len(weekly_df))
    return weekly_df


# ---------------------------------------------------------------------------
# STEP 7: INCREMENTAL LOADING
# Read existing CSV output and merge with new data, keeping the latest
# version of each date. This prevents duplicate loads when the pipeline
# reruns daily.
# ---------------------------------------------------------------------------

def incremental_upsert(new_df: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    """
    Merge new forecast data with any existing output file.
    For matching dates, the new record replaces the old one (upsert).
    For new dates, the record is appended.

    Incremental loading strategy:
    Daily weather forecasts are updated every time the pipeline runs, so
    simple append would accumulate duplicate rows for the same dates.
    This upsert pattern keeps one authoritative row per date using the
    date column as the natural key.
    """
    if output_path.exists():
        logger.info("Existing CSV found. Applying incremental upsert...")
        existing_df = pd.read_csv(output_path, parse_dates=["date"])
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)

        # Keep the latest version of each date (new data wins)
        combined_df = combined_df.drop_duplicates(subset=["date"], keep="last")
        combined_df = combined_df.sort_values("date").reset_index(drop=True)

        new_count      = len(new_df)
        existing_count = len(existing_df)
        final_count    = len(combined_df)
        logger.info(
            "Upsert complete. Existing: %s rows | New: %s rows | Final: %s rows.",
            existing_count, new_count, final_count
        )
    else:
        logger.info("No existing CSV found. Performing initial full load.")
        combined_df = new_df.sort_values("date").reset_index(drop=True)

    return combined_df


# ---------------------------------------------------------------------------
# STEP 8: DATABASE LOADING
# Load transformed data into PostgreSQL using SQLAlchemy.
# Tables are created if they don't exist. Each run upserts using MERGE
# so the pipeline is safe to rerun without duplicating rows.
# ---------------------------------------------------------------------------

def get_database_url() -> str:
    return f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def create_schema(engine) -> None:
    """Create the weather schema and all tables if they do not already exist."""
    create_sql = """
        CREATE SCHEMA IF NOT EXISTS weather;

        CREATE TABLE IF NOT EXISTS weather.locations (
            location_id     SERIAL          PRIMARY KEY,
            city            VARCHAR(100)    NOT NULL,
            state           VARCHAR(50)     NOT NULL,
            country         VARCHAR(50)     NOT NULL DEFAULT 'USA',
            latitude        NUMERIC(8, 4)   NOT NULL,
            longitude       NUMERIC(8, 4)   NOT NULL,
            timezone        VARCHAR(50)     NOT NULL,
            created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS weather.weather_codes (
            weather_code    SMALLINT        PRIMARY KEY,
            description     VARCHAR(100)    NOT NULL,
            category        VARCHAR(50)     NOT NULL
        );

        CREATE TABLE IF NOT EXISTS weather.alert_thresholds (
            threshold_id        SERIAL          PRIMARY KEY,
            alert_type          VARCHAR(50)     NOT NULL,
            alert_level         VARCHAR(50)     NOT NULL,
            metric              VARCHAR(50)     NOT NULL,
            operator            VARCHAR(10)     NOT NULL,
            threshold_value     NUMERIC(8, 2)   NOT NULL,
            unit                VARCHAR(20)     NOT NULL,
            description         TEXT,
            effective_date      DATE            NOT NULL DEFAULT CURRENT_DATE,
            UNIQUE (alert_type, alert_level)
        );

        CREATE TABLE IF NOT EXISTS weather.daily_forecasts (
            forecast_id                 SERIAL          PRIMARY KEY,
            location_id                 INTEGER         NOT NULL
                REFERENCES weather.locations(location_id),
            forecast_date               DATE            NOT NULL,
            temp_max_f                  NUMERIC(5, 1),
            temp_min_f                  NUMERIC(5, 1),
            temp_avg_f                  NUMERIC(5, 1),
            temp_range_f                NUMERIC(5, 1),
            precip_inches               NUMERIC(6, 2),
            precip_probability_pct      SMALLINT
                CHECK (precip_probability_pct BETWEEN 0 AND 100),
            wind_speed_max_mph          NUMERIC(6, 1),
            wind_gusts_max_mph          NUMERIC(6, 1),
            weather_code                SMALLINT
                REFERENCES weather.weather_codes(weather_code),
            pipeline_run_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
            data_source                 VARCHAR(100)    NOT NULL DEFAULT 'Open-Meteo API',
            UNIQUE (location_id, forecast_date)
        );

        CREATE TABLE IF NOT EXISTS weather.severe_weather_alerts (
            alert_id            SERIAL          PRIMARY KEY,
            forecast_id         INTEGER         NOT NULL
                REFERENCES weather.daily_forecasts(forecast_id),
            location_id         INTEGER         NOT NULL
                REFERENCES weather.locations(location_id),
            threshold_id        INTEGER         NOT NULL
                REFERENCES weather.alert_thresholds(threshold_id),
            alert_date          DATE            NOT NULL,
            alert_type          VARCHAR(50)     NOT NULL,
            alert_level         VARCHAR(50)     NOT NULL,
            alert_label         VARCHAR(100)    NOT NULL,
            triggered_value     NUMERIC(8, 2),
            threshold_value     NUMERIC(8, 2),
            unit                VARCHAR(20),
            created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
        );
    """
    with engine.begin() as conn:
        try:
            conn.execute(text(
                """
                TRUNCATE weather.severe_weather_alerts RESTART IDENTITY CASCADE;
                TRUNCATE weather.daily_forecasts       RESTART IDENTITY CASCADE;
                TRUNCATE weather.alert_thresholds      RESTART IDENTITY CASCADE;
                TRUNCATE weather.weather_codes         RESTART IDENTITY CASCADE;
                TRUNCATE weather.locations             RESTART IDENTITY CASCADE;
                """
            ))
            logger.info("Existing tables truncated for clean reload.")
        except Exception:
            logger.info("Tables do not exist yet, skipping truncate.")
        conn.execute(text(create_sql))
    logger.info("Schema and tables verified.")


def seed_lookup_tables(engine) -> None:
    """Insert weather codes, alert thresholds, and Cincinnati location if not already present."""

    weather_codes_data = [
        (0,  "Clear Sky",                     "Clear"),
        (1,  "Mainly Clear",                  "Clear"),
        (2,  "Partly Cloudy",                 "Cloudy"),
        (3,  "Overcast",                      "Cloudy"),
        (45, "Foggy",                         "Fog"),
        (48, "Icy Fog",                       "Fog"),
        (51, "Light Drizzle",                 "Drizzle"),
        (53, "Moderate Drizzle",              "Drizzle"),
        (55, "Dense Drizzle",                 "Drizzle"),
        (61, "Slight Rain",                   "Rain"),
        (63, "Moderate Rain",                 "Rain"),
        (65, "Heavy Rain",                    "Rain"),
        (71, "Slight Snow",                   "Snow"),
        (73, "Moderate Snow",                 "Snow"),
        (75, "Heavy Snow",                    "Snow"),
        (77, "Snow Grains",                   "Snow"),
        (80, "Slight Rain Showers",           "Rain"),
        (81, "Moderate Rain Showers",         "Rain"),
        (82, "Violent Rain Showers",          "Rain"),
        (85, "Slight Snow Showers",           "Snow"),
        (86, "Heavy Snow Showers",            "Snow"),
        (95, "Thunderstorm",                  "Storm"),
        (96, "Thunderstorm with Slight Hail", "Storm"),
        (99, "Thunderstorm with Heavy Hail",  "Storm"),
    ]

    alert_thresholds_data = [
        ("freeze", "standard", "temp_min_f",        "<=",  32.0, "F",      "Freeze Alert: low temp at or below 32F"),
        ("heat",   "standard", "temp_max_f",         ">=",  90.0, "F",      "Heat Alert: high temp at or above 90F"),
        ("heat",   "extreme",  "temp_max_f",         ">=", 100.0, "F",      "Extreme Heat Alert: high temp at or above 100F"),
        ("precip", "standard", "precip_inches",      ">=",   1.5, "inches", "Heavy Precipitation Alert: daily total >= 1.5 in"),
        ("precip", "extreme",  "precip_inches",      ">=",   3.0, "inches", "Extreme Precipitation Alert: daily total >= 3.0 in"),
        ("wind",   "standard", "wind_speed_max_mph", ">=",  35.0, "mph",    "High Wind Alert: max wind speed >= 35 mph"),
        ("wind",   "extreme",  "wind_speed_max_mph", ">=",  60.0, "mph",    "Extreme Wind Alert: max wind speed >= 60 mph"),
    ]

    with engine.begin() as conn:
        # Seed weather codes
        for code, description, category in weather_codes_data:
            conn.execute(text("""
                INSERT INTO weather.weather_codes (weather_code, description, category)
                VALUES (:code, :desc, :cat)
                ON CONFLICT (weather_code) DO NOTHING
            """), {"code": code, "desc": description, "cat": category})

        # Seed alert thresholds
        for alert_type, alert_level, metric, operator, value, unit, desc in alert_thresholds_data:
            conn.execute(text("""
                INSERT INTO weather.alert_thresholds
                    (alert_type, alert_level, metric, operator, threshold_value, unit, description)
                VALUES (:at, :al, :m, :op, :val, :unit, :desc)
                ON CONFLICT (alert_type, alert_level) DO NOTHING
            """), {"at": alert_type, "al": alert_level, "m": metric,
                   "op": operator, "val": value, "unit": unit, "desc": desc})

        # Seed Cincinnati location
        conn.execute(text("""
            INSERT INTO weather.locations (city, state, country, latitude, longitude, timezone)
            VALUES ('Cincinnati', 'Ohio', 'USA', 39.1271, -84.5144, 'America/New_York')
            ON CONFLICT DO NOTHING
        """))

    logger.info("Lookup tables seeded.")


def write_table(df: pd.DataFrame, table_name: str, engine, dtype: dict) -> None:
    """Write a DataFrame to a PostgreSQL table using SQLAlchemy."""
    logger.info("Loading %s... (%s rows)", table_name, len(df))
    df.to_sql(
        table_name,
        engine,
        schema="weather",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
        dtype=dtype,
    )


def load_alerts_with_forecast_ids(alerts_df: pd.DataFrame, engine) -> None:
    """
    Load severe weather alerts after fetching forecast_id values from the database.
    forecast_id is a SERIAL column only known after daily_forecasts is inserted,
    so we fetch the mapping and join before writing alerts.
    """
    if alerts_df.empty:
        logger.info("No alerts triggered — skipping severe_weather_alerts load.")
        return

    with engine.connect() as conn:
        id_map = pd.read_sql(
            text("SELECT forecast_id, forecast_date FROM weather.daily_forecasts"),
            conn
        )

    id_map["forecast_date"]    = pd.to_datetime(id_map["forecast_date"]).dt.date
    alerts_df["forecast_date"] = pd.to_datetime(alerts_df["forecast_date"]).dt.date
    alerts_df = alerts_df.merge(id_map, on="forecast_date", how="left").drop(columns=["forecast_date"])

    write_table(alerts_df, "severe_weather_alerts", engine, {
        "forecast_id":     Integer(),
        "location_id":     Integer(),
        "threshold_id":    Integer(),
        "alert_date":      Date(),
        "alert_type":      String(),
        "alert_level":     String(),
        "alert_label":     String(),
        "triggered_value": Numeric(8, 2),
        "threshold_value": Numeric(8, 2),
        "unit":            String(),
    })


def build_lookup_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build seed DataFrames for weather_codes, alert_thresholds, and locations."""

    weather_codes_df = pd.DataFrame([
        (0,  "Clear Sky",                     "Clear"),
        (1,  "Mainly Clear",                  "Clear"),
        (2,  "Partly Cloudy",                 "Cloudy"),
        (3,  "Overcast",                      "Cloudy"),
        (45, "Foggy",                         "Fog"),
        (48, "Icy Fog",                       "Fog"),
        (51, "Light Drizzle",                 "Drizzle"),
        (53, "Moderate Drizzle",              "Drizzle"),
        (55, "Dense Drizzle",                 "Drizzle"),
        (61, "Slight Rain",                   "Rain"),
        (63, "Moderate Rain",                 "Rain"),
        (65, "Heavy Rain",                    "Rain"),
        (71, "Slight Snow",                   "Snow"),
        (73, "Moderate Snow",                 "Snow"),
        (75, "Heavy Snow",                    "Snow"),
        (77, "Snow Grains",                   "Snow"),
        (80, "Slight Rain Showers",           "Rain"),
        (81, "Moderate Rain Showers",         "Rain"),
        (82, "Violent Rain Showers",          "Rain"),
        (85, "Slight Snow Showers",           "Snow"),
        (86, "Heavy Snow Showers",            "Snow"),
        (95, "Thunderstorm",                  "Storm"),
        (96, "Thunderstorm with Slight Hail", "Storm"),
        (99, "Thunderstorm with Heavy Hail",  "Storm"),
    ], columns=["weather_code", "description", "category"])

    alert_thresholds_df = pd.DataFrame([
        ("freeze", "standard", "temp_min_f",        "<=",  32.0, "F",      "Freeze Alert: low temp at or below 32F"),
        ("heat",   "standard", "temp_max_f",         ">=",  90.0, "F",      "Heat Alert: high temp at or above 90F"),
        ("heat",   "extreme",  "temp_max_f",         ">=", 100.0, "F",      "Extreme Heat Alert: high temp at or above 100F"),
        ("precip", "standard", "precip_inches",      ">=",   1.5, "inches", "Heavy Precipitation Alert: daily total >= 1.5 in"),
        ("precip", "extreme",  "precip_inches",      ">=",   3.0, "inches", "Extreme Precipitation Alert: daily total >= 3.0 in"),
        ("wind",   "standard", "wind_speed_max_mph", ">=",  35.0, "mph",    "High Wind Alert: max wind speed >= 35 mph"),
        ("wind",   "extreme",  "wind_speed_max_mph", ">=",  60.0, "mph",    "Extreme Wind Alert: max wind speed >= 60 mph"),
    ], columns=["alert_type", "alert_level", "metric", "operator",
                "threshold_value", "unit", "description"])
    alert_thresholds_df["threshold_id"] = alert_thresholds_df.index + 1

    locations_df = pd.DataFrame([{
        "city": "Cincinnati", "state": "Ohio", "country": "USA",
        "latitude": 39.1271, "longitude": -84.5144, "timezone": "America/New_York",
        "location_id": 1,
    }])

    return weather_codes_df, alert_thresholds_df, locations_df


def build_forecast_df(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare the daily_forecasts DataFrame for database loading."""
    forecast_df = df[[
        "date", "temp_max_f", "temp_min_f", "temp_avg_f", "temp_range_f",
        "precip_inches", "precip_probability_pct",
        "wind_speed_max_mph", "wind_gusts_max_mph", "weather_code",
    ]].copy()
    forecast_df = forecast_df.rename(columns={"date": "forecast_date"})
    forecast_df["forecast_date"] = pd.to_datetime(forecast_df["forecast_date"]).dt.date
    forecast_df.insert(0, "location_id", 1)
    forecast_df["data_source"] = "Open-Meteo API"
    return forecast_df


def build_alerts_df(
    df: pd.DataFrame,
    alert_thresholds_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the severe_weather_alerts DataFrame from triggered alert rows."""
    threshold_lookup = {
        (r["alert_type"], r["alert_level"]): (r["threshold_id"], r["threshold_value"], r["unit"])
        for _, r in alert_thresholds_df.iterrows()
    }

    t = THRESHOLDS
    alert_rows = []

    for _, row in df.iterrows():
        candidates = [
            (row["temp_min_f"] <= t["freeze_temp_f"],
             "freeze", "standard", "Freeze Alert", row["temp_min_f"]),
            (row["temp_max_f"] >= t["extreme_heat_temp_f"],
             "heat", "extreme", "Extreme Heat Alert", row["temp_max_f"]),
            (t["heat_temp_f"] <= row["temp_max_f"] < t["extreme_heat_temp_f"],
             "heat", "standard", "Heat Alert", row["temp_max_f"]),
            (row["precip_inches"] >= t["extreme_precip_in"],
             "precip", "extreme", "Extreme Precipitation Alert", row["precip_inches"]),
            (t["heavy_precip_in"] <= row["precip_inches"] < t["extreme_precip_in"],
             "precip", "standard", "Heavy Precipitation Alert", row["precip_inches"]),
            (row["wind_speed_max_mph"] >= t["extreme_wind_mph"],
             "wind", "extreme", "Extreme Wind Alert", row["wind_speed_max_mph"]),
            (t["high_wind_mph"] <= row["wind_speed_max_mph"] < t["extreme_wind_mph"],
             "wind", "standard", "High Wind Alert", row["wind_speed_max_mph"]),
        ]
        for condition, alert_type, alert_level, label, triggered_value in candidates:
            if condition:
                key = (alert_type, alert_level)
                if key in threshold_lookup:
                    tid, tval, unit = threshold_lookup[key]
                    alert_rows.append({
                        "forecast_date":   pd.to_datetime(row["date"]).date(),
                        "location_id":     1,
                        "threshold_id":    tid,
                        "alert_date":      pd.to_datetime(row["date"]).date(),
                        "alert_type":      alert_type,
                        "alert_level":     alert_level,
                        "alert_label":     label,
                        "triggered_value": triggered_value,
                        "threshold_value": tval,
                        "unit":            unit,
                    })

    return pd.DataFrame(alert_rows)


def load_to_database(df: pd.DataFrame) -> None:
    """
    Load all transformed data into PostgreSQL.
    Creates schema, seeds lookup tables, and loads forecast and alert data.
    """
    logger.info("Connecting to PostgreSQL...")
    engine = create_engine(get_database_url())

    create_schema(engine)
    seed_lookup_tables(engine)

    weather_codes_df, alert_thresholds_df, locations_df = build_lookup_tables()
    forecast_df = build_forecast_df(df)
    alerts_df   = build_alerts_df(df, alert_thresholds_df)

    # Lookup tables (weather_codes, alert_thresholds, locations) are already
    # seeded by seed_lookup_tables() above using ON CONFLICT DO NOTHING.
    # Only the fact tables need write_table here.
    write_table(forecast_df, "daily_forecasts", engine, {
        "location_id": Integer(), "forecast_date": Date(),
        "temp_max_f": Numeric(5, 1), "temp_min_f": Numeric(5, 1),
        "temp_avg_f": Numeric(5, 1), "temp_range_f": Numeric(5, 1),
        "precip_inches": Numeric(6, 2), "precip_probability_pct": SmallInteger(),
        "wind_speed_max_mph": Numeric(6, 1), "wind_gusts_max_mph": Numeric(6, 1),
        "weather_code": SmallInteger(), "data_source": String(),
    })
    load_alerts_with_forecast_ids(alerts_df, engine)

    # Referential integrity check: confirm all forecast rows loaded
    with engine.connect() as conn:
        db_count = conn.execute(
            text("SELECT COUNT(*) FROM weather.daily_forecasts")
        ).scalar()
    if db_count < len(forecast_df):
        logger.warning(
            "Referential integrity check: expected %s rows in daily_forecasts, found %s.",
            len(forecast_df), db_count
        )
    else:
        logger.info("Referential integrity check passed. %s rows in daily_forecasts.", db_count)


# ---------------------------------------------------------------------------
# STEP 9: CSV OUTPUT FOR POWER BI
# Save the finalized dataset as a CSV that Power BI can connect to directly.
# Uses incremental upsert so daily reruns don't overwrite historical data.
# ---------------------------------------------------------------------------

def load_to_csv(df: pd.DataFrame) -> None:
    """Save the finalized forecast DataFrame to CSV using incremental upsert."""
    final_df = incremental_upsert(df, OUTPUT_PATH)
    final_df.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    logger.info("CSV saved to %s (%s rows).", OUTPUT_PATH, len(final_df))


# ---------------------------------------------------------------------------
# MAIN
# Orchestrates the full ETL pipeline:
#   Extract → Validate → Clean → Transform → Validate → Aggregate → Load
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the complete ETL pipeline from extraction through database load."""
    logger.info("=" * 60)
    logger.info("  Cincinnati Weather ETL Pipeline — Starting")
    logger.info("=" * 60)

    start_time = datetime.now()

    try:
        # Extract
        raw_data = extract_weather_data()

        # Validate raw response
        validate_raw_response(raw_data)

        # Clean and normalize
        df = clean_and_normalize(raw_data)

        # Transform and derive metrics
        df = transform_and_derive_metrics(df)

        # Validate clean data
        validate_clean_forecast(df)

        # Build weekly aggregation layer
        weekly_df = build_weekly_aggregation(df)

        # Load to CSV (incremental upsert for Power BI)
        load_to_csv(df)

        # Load to PostgreSQL
        load_to_database(df)

        elapsed      = (datetime.now() - start_time).total_seconds()
        severe_days  = int(df["severe_weather_day"].sum())

        logger.info("─" * 60)
        logger.info("  Pipeline completed in %.2f seconds", elapsed)
        logger.info("  Forecast range  : %s → %s", df["date"].min().date(), df["date"].max().date())
        logger.info("  Total rows      : %s", len(df))
        logger.info("  Severe wx days  : %s of %s", severe_days, len(df))
        logger.info("  Weekly buckets  : %s", len(weekly_df))
        logger.info("  Output CSV      : %s", OUTPUT_PATH)
        logger.info("─" * 60)

        logger.info("Sample forecast rows:\n%s", df[[
            "date", "temp_max_f", "temp_min_f", "precip_inches",
            "wind_speed_max_mph", "weather_description", "severe_weather_day"
        ]].head().to_string(index=False))

        logger.info("Sample weekly summary:\n%s", weekly_df.head().to_string())

    except Exception:
        # Error handling example:
        # Log the full traceback then re-raise so automation tools correctly
        # mark the pipeline run as failed.
        logger.exception("ETL pipeline failed.")
        raise


if __name__ == "__main__":
    main()
