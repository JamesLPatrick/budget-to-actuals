# Budget-to-Actuals Analytics Engineering Pipeline

An end-to-end analytics engineering pipeline simulating a monthly financial close: a one-time budget load, a Python-generated "actuals" feed mimicking ERP month-end exports, dbt models with an incremental fact table, and a Tableau variance dashboard.

## Why this exists
A hands-on project to build practical analytics engineering skills using tools relevant to a Databricks + AWS environment, applied to a domain (budget vs. actuals reporting) grounded in real FP&A work.

## Architecture
```
Python generator  →  Databricks (raw)  →  dbt staging  →  dbt marts  →  Tableau
  (simulated ERP        (Unity Catalog)     (cleaned)     (incremental,     (variance
   month-end export)                                       tested)          dashboard)
```

## Tech Stack
- **Python** — data generation, loading
- **Databricks Free Edition** — warehouse/compute (Unity Catalog)
- **dbt Core** (`dbt-databricks`) — transformation, testing, documentation
- **Tableau Desktop Free Edition** — BI/dashboard layer
- **Git/GitHub** — version control

## What it demonstrates
- Dimensional modeling (staging → dims/facts)
- Incremental materialization with merge-based upserts, verified across multiple simulated load periods
- Data quality testing (not-null, uniqueness, referential integrity)
- A repeatable, source-to-dashboard pipeline rather than a one-off analysis

## Status
In progress — built over a 5-week timeline (Aug–Sep 2026).

## Roadmap
A planned follow-on project extends this into a simulated small business with multiple departments and revenue/expense source systems, adding Airflow orchestration and CI/CD.