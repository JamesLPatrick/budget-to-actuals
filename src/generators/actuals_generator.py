"""
actuals_generator.py

Simulates the monthly actuals feed that would normally arrive from various
business systems and get manually uploaded into Hyperion at month-end.
Reads the budgeted baseline for the target month directly from Databricks,
applies randomized variance, writes a landing CSV (mimicking an ERP export),
and loads the result into Databricks as "actuals_raw".

Usage:
    python actuals_generator.py                 # generates for the current month
    python actuals_generator.py --month 2026-09 # generates for a specific month
"""

import argparse
import csv
import os
import random
import uuid
from datetime import date
from pathlib import Path

from databricks import sql
from dotenv import load_dotenv

load_dotenv()  # reads .env for local credentials — .env is gitignored, never committed

# ---- Config ----
DATABRICKS_HOST = os.environ["DATABRICKS_HOST"]
DATABRICKS_HTTP_PATH = os.environ["DATABRICKS_HTTP_PATH"]
DATABRICKS_TOKEN = os.environ["DATABRICKS_TOKEN"]

CATALOG = "workspace"
SCHEMA = "budget_to_actuals"
BUDGET_TABLE = "budget"
RAW_TABLE = "actuals_raw"

LANDING_DIR = Path("data/raw")

# ---- Variance model ----
NORMAL_VARIANCE_STD = 0.08      # ~8% typical noise on most line items
SURPRISE_CHANCE = 0.10          # 10% of line items get a bigger swing
SURPRISE_RANGE = (0.25, 0.45)   # 25-45% swing when a surprise hits


def parse_args():
    parser = argparse.ArgumentParser(description="Generate simulated monthly actuals.")
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="Target period as YYYY-MM. Defaults to the current month.",
    )
    args = parser.parse_args()

    if args.month:
        year, month = args.month.split("-")
        return int(year), int(month)
    today = date.today()
    return today.year, today.month


def get_connection():
    return sql.connect(
        server_hostname=DATABRICKS_HOST,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
        catalog=CATALOG,
        schema=SCHEMA,
    )


def fetch_budget_baseline(conn, fiscal_year, month):
    query = f"""
        SELECT cost_center_id, cost_center_name, account_id, account_name, budget_amount
        FROM {BUDGET_TABLE}
        WHERE fiscal_year = ? AND month = ?
    """
    with conn.cursor() as cur:
        cur.execute(query, [fiscal_year, month])
        return cur.fetchall()


def apply_variance(budget_amount):
    if random.random() < SURPRISE_CHANCE:
        pct = random.uniform(*SURPRISE_RANGE)
        sign = random.choice([-1, 1])
        factor = 1 + (sign * pct)
    else:
        factor = 1 + random.gauss(0, NORMAL_VARIANCE_STD)
    return round(float(budget_amount) * factor, 2)


def build_actuals_rows(budget_rows, fiscal_year, month, batch_id):
    rows = []
    for cc_id, cc_name, acct_id, acct_name, budget_amount in budget_rows:
        actual = apply_variance(budget_amount)
        rows.append((cc_id, cc_name, acct_id, acct_name, fiscal_year, month, actual, batch_id))
    return rows


def write_landing_csv(rows, fiscal_year, month):
    LANDING_DIR.mkdir(parents=True, exist_ok=True)
    filepath = LANDING_DIR / f"actuals_{fiscal_year}_{month:02d}.csv"
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["cost_center_id", "cost_center_name", "account_id", "account_name",
             "fiscal_year", "month", "actual_amount", "load_batch_id"]
        )
        writer.writerows(rows)
    print(f"Wrote landing file: {filepath}")
    return filepath


def ensure_raw_table(conn):
    ddl = f"""
        CREATE TABLE IF NOT EXISTS {RAW_TABLE} (
            cost_center_id STRING,
            cost_center_name STRING,
            account_id STRING,
            account_name STRING,
            fiscal_year INT,
            month INT,
            actual_amount DOUBLE,
            load_batch_id STRING,
            loaded_at TIMESTAMP
        )
    """
    with conn.cursor() as cur:
        cur.execute(ddl)


def load_to_databricks(conn, rows, fiscal_year, month):
    with conn.cursor() as cur:
        # delete any prior load for this period first, so re-running the
        # same month replaces it instead of creating duplicate rows
        cur.execute(
            f"DELETE FROM {RAW_TABLE} WHERE fiscal_year = ? AND month = ?",
            [fiscal_year, month],
        )
        insert_sql = f"""
            INSERT INTO {RAW_TABLE}
            (cost_center_id, cost_center_name, account_id, account_name,
             fiscal_year, month, actual_amount, load_batch_id, loaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp())
        """
        cur.executemany(insert_sql, rows)
    print(f"Loaded {len(rows)} rows into {RAW_TABLE} for {fiscal_year}-{month:02d}")


def main():
    fiscal_year, month = parse_args()
    batch_id = f"batch_{fiscal_year}_{month:02d}_{uuid.uuid4().hex[:8]}"

    conn = get_connection()
    try:
        ensure_raw_table(conn)
        budget_rows = fetch_budget_baseline(conn, fiscal_year, month)
        if not budget_rows:
            raise ValueError(
                f"No budget found for {fiscal_year}-{month:02d}. "
                f"Check that dbt seed loaded the budget table for this period."
            )
        actuals_rows = build_actuals_rows(budget_rows, fiscal_year, month, batch_id)
        write_landing_csv(actuals_rows, fiscal_year, month)
        load_to_databricks(conn, actuals_rows, fiscal_year, month)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
