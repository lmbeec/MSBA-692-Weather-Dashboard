# MSBA-692-Weather-Dashboard

An interactive weather monitoring dashboard built with Plotly Dash and PostgreSQL. Extracts 16-day daily forecast data from the Open-Meteo API, processes it through a Python ETL pipeline, loads it into a relational database, and visualizes it in a multi-page interactive web application.

---

## How to Run

### 1. Install Dependencies
```
pip install requests pandas sqlalchemy psycopg2-binary dash plotly
```

### 2. Configure Database
Open both scripts and update the credentials at the top:
```python
DB_HOST     = "localhost"
DB_NAME     = "Logan"
DB_USER     = "postgres"
DB_PASSWORD = "your_password"
```

### 3. Run the ETL Pipeline
```
python cincinnati_weather_etl.py
```

### 4. Run the Dashboard
```
python dashboard.py
```

### 5. Open in Browser
```
http://127.0.0.1:8050
```
The dashboard runs locally and stays active while Command Prompt is open.

---

## Dependencies

| Package | Purpose |
|---|---|
| requests | Fetch data from Open-Meteo API |
| pandas | Data transformation and cleaning |
| sqlalchemy | PostgreSQL database connection |
| psycopg2-binary | PostgreSQL driver |
| dash | Web application framework |
| plotly | Interactive chart library |

---

## Dashboard Pages

| Page | Contents |
|---|---|
| Overview | 5 KPI cards, temperature trend line chart, weather condition breakdown |
| Temperature | High/low/avg trend with alert threshold lines, daily temperature swing chart |
| Precipitation | Daily rainfall bars with alert lines, precipitation probability area chart |
| Wind | Wind speed and gust chart with severity color coding and alert threshold lines |
| Severe Weather | Alert count KPIs, alert timeline scatter chart, detailed triggered alerts table |

---

## Interactivity

- **Date Range Slider** — filters all charts and KPI cards across every page simultaneously
- **Hover Tooltips** — hover over any data point to see exact values
- **Tab Navigation** — switch between 5 pages without restarting the app

---

## Severe Weather Alert Thresholds

| Alert Type | Level | Condition |
|---|---|---|
| Freeze | Standard | Low temp ≤ 32°F |
| Heat | Standard | High temp ≥ 90°F |
| Heat | Extreme | High temp ≥ 100°F |
| Precipitation | Standard | Daily total ≥ 1.5 inches |
| Precipitation | Extreme | Daily total ≥ 3.0 inches |
| Wind | Standard | Max speed ≥ 35 mph |
| Wind | Extreme | Max speed ≥ 60 mph |

---

## Business Insights

**Temperature Planning** — Identify upcoming heat waves or cold snaps up to 16 days in advance for event planning.

**Precipitation Awareness** — Daily totals and probability charts support outdoor activity planning, construction scheduling, and flood risk awareness in Cincinnati.

**Wind Safety** — Color-coded severity indicators help residents and businesses plan around high-wind days before they occur.

**Centralized Severe Weather Monitoring** — Consolidates freeze, heat, precipitation, and wind thresholds into one view. Each alert traces back to the exact threshold value that triggered it.

---

## Project Files

| File | Purpose |
|---|---|
| `cincinnati_weather_etl.py` | ETL pipeline — extract, transform, validate, and load weather data |
| `dashboard.py` | Plotly Dash dashboard — 5-page interactive web application |
| `README.md` | Project documentation |

---

## Data Source

- **API:** Open-Meteo (https://open-meteo.com/) — free, no API key required
- **Location:** Cincinnati, OH (39.1271°N, 84.5144°W)
- **Forecast:** 16-day daily forecast
- **Units:** Fahrenheit, inches, mph
