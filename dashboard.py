"""
Cincinnati Weather Dashboard — Plotly Dash
==========================================
Run with:  python dashboard.py
Then open: http://127.0.0.1:8050

Dependencies:
    pip install dash plotly pandas sqlalchemy psycopg2-binary
"""

import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install",
    "dash", "plotly", "pandas", "sqlalchemy", "psycopg2-binary"], stdout=subprocess.DEVNULL)

from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from sqlalchemy import create_engine, text

# ─────────────────────────────────────────────
# DATABASE CONFIGURATION
# ─────────────────────────────────────────────

DB_HOST     = "localhost"
DB_PORT     = 5432
DB_NAME     = "Logan"
DB_USER     = "postgres"
DB_PASSWORD = "Incorrect11*"

def get_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)

def load_data():
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT
                df.forecast_date,
                df.temp_max_f,
                df.temp_min_f,
                df.temp_avg_f,
                df.temp_range_f,
                df.precip_inches,
                df.precip_probability_pct,
                df.wind_speed_max_mph,
                df.wind_gusts_max_mph,
                df.weather_code,
                wc.description AS weather_description,
                wc.category    AS weather_category
            FROM weather.daily_forecasts df
            LEFT JOIN weather.weather_codes wc ON df.weather_code = wc.weather_code
            ORDER BY df.forecast_date
        """), conn)

        alerts_df = pd.read_sql(text("""
            SELECT alert_date, alert_type, alert_level, alert_label,
                   triggered_value, threshold_value, unit
            FROM weather.severe_weather_alerts
            ORDER BY alert_date
        """), conn)

    df["forecast_date"] = pd.to_datetime(df["forecast_date"])
    alerts_df["alert_date"] = pd.to_datetime(alerts_df["alert_date"])
    return df, alerts_df

# ─────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────

BG          = "#0a0e1a"
CARD_BG     = "#111827"
CARD_BG2    = "#1a2235"
BORDER      = "#1e3a5f"
ACCENT      = "#38bdf8"
ACCENT2     = "#f97316"
ACCENT3     = "#22d3ee"
TEXT        = "#e2e8f0"
TEXT_DIM    = "#94a3b8"
RED         = "#ef4444"
YELLOW      = "#eab308"
GREEN       = "#22c55e"
PURPLE      = "#a855f7"

PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="'DM Mono', monospace", color=TEXT, size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    xaxis=dict(gridcolor="#1e3a5f", tickcolor=TEXT_DIM, linecolor=BORDER, zeroline=False),
    yaxis=dict(gridcolor="#1e3a5f", tickcolor=TEXT_DIM, linecolor=BORDER, zeroline=False),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_DIM)),
    hoverlabel=dict(bgcolor=CARD_BG2, font_color=TEXT, bordercolor=BORDER),
)

def card(children, style=None):
    base = dict(
        background=CARD_BG,
        border=f"1px solid {BORDER}",
        borderRadius="12px",
        padding="20px",
        marginBottom="16px",
    )
    if style:
        base.update(style)
    return html.Div(children, style=base)

def kpi(label, value, color=ACCENT, sub=None):
    return html.Div([
        html.Div(label, style=dict(color=TEXT_DIM, fontSize="11px", letterSpacing="2px",
                                   textTransform="uppercase", marginBottom="8px", fontFamily="'DM Mono', monospace")),
        html.Div(value, style=dict(color=color, fontSize="32px", fontWeight="700",
                                   fontFamily="'DM Mono', monospace", lineHeight="1")),
        html.Div(sub or "", style=dict(color=TEXT_DIM, fontSize="11px", marginTop="6px",
                                       fontFamily="'DM Mono', monospace")),
    ], style=dict(
        background=CARD_BG2,
        border=f"1px solid {BORDER}",
        borderRadius="10px",
        padding="20px",
        flex="1",
        minWidth="140px",
    ))

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────

try:
    df, alerts_df = load_data()
    DATA_OK = True
except Exception as e:
    DATA_OK = False
    DATA_ERROR = str(e)
    df = pd.DataFrame()
    alerts_df = pd.DataFrame()

# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "Cincinnati Weather Dashboard"

NAV_TABS = ["Overview", "Temperature", "Precipitation", "Wind", "Severe Weather"]

app.layout = html.Div([
    # Google Fonts
    html.Link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&display=swap"),

    # Header
    html.Div([
        html.Div([
            html.Div("◈", style=dict(color=ACCENT, fontSize="28px", marginRight="12px")),
            html.Div([
                html.Div("CINCINNATI WEATHER", style=dict(
                    fontFamily="'Syne', sans-serif", fontSize="22px",
                    fontWeight="800", color=TEXT, letterSpacing="3px")),
                html.Div("TREND & SEVERE WEATHER MONITORING DASHBOARD", style=dict(
                    fontFamily="'DM Mono', monospace", fontSize="10px",
                    color=TEXT_DIM, letterSpacing="2px")),
            ]),
        ], style=dict(display="flex", alignItems="center")),
        html.Div(
            f"Cincinnati, OH  ·  39.1271°N 84.5144°W  ·  {len(df)} day forecast" if DATA_OK else "— data unavailable —",
            style=dict(fontFamily="'DM Mono', monospace", fontSize="11px", color=TEXT_DIM)
        ),
    ], style=dict(
        display="flex", justifyContent="space-between", alignItems="center",
        padding="20px 32px", borderBottom=f"1px solid {BORDER}",
        background=CARD_BG, position="sticky", top="0", zIndex="100",
    )),

    # Nav tabs
    html.Div([
        html.Div([
            html.Button(tab, id=f"tab-{tab.lower().replace(' ', '-')}", n_clicks=0,
                style=dict(
                    background="transparent", border="none", cursor="pointer",
                    fontFamily="'DM Mono', monospace", fontSize="12px",
                    color=TEXT_DIM, padding="12px 20px", letterSpacing="1px",
                    textTransform="uppercase",
                ))
            for tab in NAV_TABS
        ], style=dict(display="flex")),
    ], style=dict(
        borderBottom=f"1px solid {BORDER}",
        background=CARD_BG, paddingLeft="20px",
    )),

    # Date range slider
    html.Div([
        html.Div("FORECAST DATE RANGE", style=dict(
            color=TEXT_DIM, fontSize="10px", letterSpacing="2px",
            marginBottom="8px", fontFamily="'DM Mono', monospace"
        )),
        dcc.RangeSlider(
            id="date-slider",
            min=0,
            max=len(df) - 1 if DATA_OK else 15,
            value=[0, len(df) - 1 if DATA_OK else 15],
            marks={i: {"label": df["forecast_date"].iloc[i].strftime("%b %d") if DATA_OK else str(i),
                       "style": {"color": TEXT_DIM, "fontSize": "10px", "fontFamily": "'DM Mono', monospace"}}
                   for i in range(0, len(df) if DATA_OK else 16, 2)},
            tooltip={"always_visible": False},
        ),
    ], style=dict(
        padding="16px 32px 8px 32px",
        borderBottom=f"1px solid {BORDER}",
        background=CARD_BG,
    )),

    # Page content
    html.Div(id="page-content", style=dict(padding="24px 32px")),

    # Store active tab
    dcc.Store(id="active-tab", data="Overview", storage_type="memory"),

], style=dict(
    background=BG, minHeight="100vh", color=TEXT,
    fontFamily="'DM Mono', monospace",
))


# ─────────────────────────────────────────────
# TAB CALLBACK
# ─────────────────────────────────────────────

@app.callback(
    Output("active-tab", "data"),
    [Input(f"tab-{tab.lower().replace(' ', '-')}", "n_clicks") for tab in NAV_TABS],

)
def update_active_tab(*args):
    from dash import ctx
    if not ctx.triggered:
        return "Overview"
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    mapping = {f"tab-{tab.lower().replace(' ', '-')}": tab for tab in NAV_TABS}
    return mapping.get(button_id, "Overview")


# ─────────────────────────────────────────────
# PAGE RENDER CALLBACK
# ─────────────────────────────────────────────

@app.callback(
    Output("page-content", "children"),
    Input("active-tab", "data"),
    Input("date-slider", "value"),
)
def render_page(tab, date_range):
    if tab is None:
        tab = "Overview"
    if date_range is None or not DATA_OK:
        date_range = [0, len(df) - 1]

    # Filter dataframe based on slider
    start_idx, end_idx = date_range
    filtered_df = df.iloc[start_idx:end_idx + 1].copy()
    filtered_alerts = alerts_df[
        (alerts_df["alert_date"] >= filtered_df["forecast_date"].min()) &
        (alerts_df["alert_date"] <= filtered_df["forecast_date"].max())
    ].copy() if not alerts_df.empty and not filtered_df.empty else alerts_df.copy()
    if not DATA_OK:
        return html.Div(f"Database connection error: {DATA_ERROR}",
                        style=dict(color=RED, padding="40px"))

    if tab == "Overview":
        return render_overview(filtered_df, filtered_alerts)
    elif tab == "Temperature":
        return render_temperature(filtered_df)
    elif tab == "Precipitation":
        return render_precipitation(filtered_df)
    elif tab == "Wind":
        return render_wind(filtered_df)
    elif tab == "Severe Weather":
        return render_severe_weather(filtered_df, filtered_alerts)


# ─────────────────────────────────────────────
# PAGE 1 — OVERVIEW
# ─────────────────────────────────────────────

def render_overview(df, alerts_df):
    max_temp     = df["temp_max_f"].max()
    min_temp     = df["temp_min_f"].min()
    total_precip = df["precip_inches"].sum()
    max_wind     = df["wind_speed_max_mph"].max()
    severe_days  = len(alerts_df["alert_date"].unique()) if not alerts_df.empty else 0

    hottest_day  = df.loc[df["temp_max_f"].idxmax(), "forecast_date"].strftime("%b %d")
    coldest_day  = df.loc[df["temp_min_f"].idxmin(), "forecast_date"].strftime("%b %d")
    windiest_day = df.loc[df["wind_speed_max_mph"].idxmax(), "forecast_date"].strftime("%b %d")

    # Temperature trend
    fig_temp = go.Figure()
    fig_temp.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["temp_max_f"],
        name="High", line=dict(color=ACCENT2, width=2.5),
        fill=None, mode="lines+markers",
        marker=dict(size=5, color=ACCENT2),
    ))
    fig_temp.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["temp_min_f"],
        name="Low", line=dict(color=ACCENT, width=2.5),
        fill="tonexty", fillcolor="rgba(56,189,248,0.07)",
        mode="lines+markers", marker=dict(size=5, color=ACCENT),
    ))
    fig_temp.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["temp_avg_f"],
        name="Avg", line=dict(color=TEXT_DIM, width=1.5, dash="dot"),
        mode="lines",
    ))
    fig_temp.update_layout(**PLOT_LAYOUT, title=dict(text="Temperature Forecast (°F)", font=dict(color=TEXT_DIM, size=13)))

    # Weather summary bar
    weather_counts = df["weather_description"].value_counts().reset_index()
    weather_counts.columns = ["condition", "days"]
    fig_wx = go.Figure(go.Bar(
        x=weather_counts["days"], y=weather_counts["condition"],
        orientation="h",
        marker=dict(color=ACCENT, opacity=0.8),
        text=weather_counts["days"].apply(lambda x: f"{x}d"),
        textposition="outside", textfont=dict(color=TEXT_DIM, size=11),
    ))
    fig_wx.update_layout(**PLOT_LAYOUT,
        title=dict(text="Weather Condition Breakdown", font=dict(color=TEXT_DIM, size=13)),
        height=300,
    )

    return html.Div([
        # KPI row
        html.Div([
            kpi("Highest Temp", f"{max_temp:.1f}°F", ACCENT2, f"on {hottest_day}"),
            kpi("Lowest Temp",  f"{min_temp:.1f}°F",  ACCENT,  f"on {coldest_day}"),
            kpi("Total Precip", f"{total_precip:.2f}\"", ACCENT3),
            kpi("Max Wind",     f"{max_wind:.1f} mph",  PURPLE,  f"on {windiest_day}"),
            kpi("Severe Days",  str(severe_days), RED if severe_days > 0 else GREEN),
        ], style=dict(display="flex", gap="12px", marginBottom="20px", flexWrap="wrap")),

        card(dcc.Graph(figure=fig_temp, config=dict(displayModeBar=False))),
        card(dcc.Graph(figure=fig_wx,   config=dict(displayModeBar=False))),
    ])


# ─────────────────────────────────────────────
# PAGE 2 — TEMPERATURE
# ─────────────────────────────────────────────

def render_temperature(df):
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["temp_max_f"],
        name="Daily High", line=dict(color=ACCENT2, width=3),
        mode="lines+markers", marker=dict(size=7, color=ACCENT2),
    ))
    fig1.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["temp_min_f"],
        name="Daily Low", line=dict(color=ACCENT, width=3),
        fill="tonexty", fillcolor="rgba(56,189,248,0.08)",
        mode="lines+markers", marker=dict(size=7, color=ACCENT),
    ))
    fig1.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["temp_avg_f"],
        name="Daily Avg", line=dict(color=TEXT_DIM, width=2, dash="dot"),
        mode="lines",
    ))
    # Add threshold lines
    fig1.add_hline(y=90, line_dash="dash", line_color=RED,    annotation_text="Heat Alert 90°F",    annotation_font_color=RED)
    fig1.add_hline(y=32, line_dash="dash", line_color=ACCENT, annotation_text="Freeze Alert 32°F",  annotation_font_color=ACCENT)
    fig1.update_layout(**PLOT_LAYOUT, title=dict(text="Daily Temperature Range (°F)", font=dict(color=TEXT_DIM, size=13)), height=380)

    fig2 = go.Figure(go.Bar(
        x=df["forecast_date"], y=df["temp_range_f"],
        marker=dict(
            color=df["temp_range_f"],
            colorscale=[[0, ACCENT], [0.5, PURPLE], [1, ACCENT2]],
            showscale=False,
        ),
        text=df["temp_range_f"].apply(lambda x: f"{x:.1f}°"),
        textposition="outside", textfont=dict(color=TEXT_DIM, size=10),
    ))
    fig2.update_layout(**PLOT_LAYOUT,
        title=dict(text="Daily Temperature Range Spread (°F)", font=dict(color=TEXT_DIM, size=13)),
        height=300,
    )

    avg_temp = df["temp_avg_f"].mean()
    max_temp = df["temp_max_f"].max()
    min_temp = df["temp_min_f"].min()
    hottest  = df.loc[df["temp_max_f"].idxmax(), "forecast_date"].strftime("%b %d")
    coldest  = df.loc[df["temp_min_f"].idxmin(), "forecast_date"].strftime("%b %d")

    return html.Div([
        html.Div([
            kpi("Period Average",  f"{avg_temp:.1f}°F",  ACCENT),
            kpi("Highest Forecast",f"{max_temp:.1f}°F",  ACCENT2, f"on {hottest}"),
            kpi("Lowest Forecast", f"{min_temp:.1f}°F",  ACCENT,  f"on {coldest}"),
            kpi("Avg Daily Swing", f"{df['temp_range_f'].mean():.1f}°F", PURPLE),
        ], style=dict(display="flex", gap="12px", marginBottom="20px", flexWrap="wrap")),
        card(dcc.Graph(figure=fig1, config=dict(displayModeBar=False))),
        card(dcc.Graph(figure=fig2, config=dict(displayModeBar=False))),
    ])


# ─────────────────────────────────────────────
# PAGE 3 — PRECIPITATION
# ─────────────────────────────────────────────

def render_precipitation(df):
    colors = [ACCENT if p > 0 else CARD_BG2 for p in df["precip_inches"]]

    fig1 = go.Figure()
    fig1.add_trace(go.Bar(
        x=df["forecast_date"], y=df["precip_inches"],
        name="Precipitation (in)",
        marker=dict(color=colors, line=dict(color=BORDER, width=0.5)),
        text=df["precip_inches"].apply(lambda x: f"{x:.2f}\"" if x > 0 else ""),
        textposition="outside", textfont=dict(color=TEXT_DIM, size=10),
    ))
    fig1.add_hline(y=1.5, line_dash="dash", line_color=YELLOW,
                   annotation_text="Heavy Precip Alert 1.5\"", annotation_font_color=YELLOW)
    fig1.add_hline(y=3.0, line_dash="dash", line_color=RED,
                   annotation_text="Extreme Precip Alert 3.0\"", annotation_font_color=RED)
    fig1.update_layout(**PLOT_LAYOUT,
        title=dict(text="Daily Precipitation (inches)", font=dict(color=TEXT_DIM, size=13)),
        height=340,
    )

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["precip_probability_pct"],
        fill="tozeroy", fillcolor="rgba(56,189,248,0.1)",
        line=dict(color=ACCENT, width=2.5),
        mode="lines+markers", marker=dict(size=6, color=ACCENT),
        name="Rain Probability (%)",
    ))
    fig2.update_layout(**PLOT_LAYOUT,
        title=dict(text="Precipitation Probability (%)", font=dict(color=TEXT_DIM, size=13)),
        height=280,
    )
    fig2.update_yaxes(range=[0, 105], gridcolor="#1e3a5f")

    rainy_days   = (df["precip_inches"] > 0).sum()
    total_precip = df["precip_inches"].sum()
    max_precip   = df["precip_inches"].max()
    max_prob     = df["precip_probability_pct"].max()
    wettest_day  = df.loc[df["precip_inches"].idxmax(), "forecast_date"].strftime("%b %d")

    return html.Div([
        html.Div([
            kpi("Total Precipitation", f"{total_precip:.2f}\"", ACCENT),
            kpi("Rainy Days",          str(rainy_days),          ACCENT3),
            kpi("Max Single Day",      f"{max_precip:.2f}\"",    ACCENT2, f"on {wettest_day}"),
            kpi("Max Rain Chance",     f"{max_prob:.0f}%",       PURPLE),
        ], style=dict(display="flex", gap="12px", marginBottom="20px", flexWrap="wrap")),
        card(dcc.Graph(figure=fig1, config=dict(displayModeBar=False))),
        card(dcc.Graph(figure=fig2, config=dict(displayModeBar=False))),
    ])


# ─────────────────────────────────────────────
# PAGE 4 — WIND
# ─────────────────────────────────────────────

def render_wind(df):
    wind_colors = []
    for w in df["wind_speed_max_mph"]:
        if w >= 60:   wind_colors.append(RED)
        elif w >= 35: wind_colors.append(YELLOW)
        else:         wind_colors.append(ACCENT)

    fig1 = go.Figure()
    fig1.add_trace(go.Bar(
        x=df["forecast_date"], y=df["wind_speed_max_mph"],
        name="Max Wind Speed",
        marker=dict(color=wind_colors),
        text=df["wind_speed_max_mph"].apply(lambda x: f"{x:.1f}"),
        textposition="outside", textfont=dict(color=TEXT_DIM, size=10),
    ))
    fig1.add_trace(go.Scatter(
        x=df["forecast_date"], y=df["wind_gusts_max_mph"],
        name="Max Gusts", line=dict(color=ACCENT2, width=2, dash="dot"),
        mode="lines+markers", marker=dict(size=5, color=ACCENT2),
    ))
    fig1.add_hline(y=35, line_dash="dash", line_color=YELLOW,
                   annotation_text="High Wind Alert 35 mph", annotation_font_color=YELLOW)
    fig1.add_hline(y=60, line_dash="dash", line_color=RED,
                   annotation_text="Extreme Wind Alert 60 mph", annotation_font_color=RED)
    fig1.update_layout(**PLOT_LAYOUT,
        title=dict(text="Wind Speed & Gusts (mph)", font=dict(color=TEXT_DIM, size=13)),
        height=380,
    )

    fig2 = go.Figure(go.Scatter(
        x=df["forecast_date"], y=df["wind_gusts_max_mph"],
        fill="tozeroy", fillcolor="rgba(249,115,22,0.08)",
        line=dict(color=ACCENT2, width=2),
        mode="lines+markers", marker=dict(size=6, color=ACCENT2),
    ))
    fig2.update_layout(**PLOT_LAYOUT,
        title=dict(text="Wind Gust Forecast (mph)", font=dict(color=TEXT_DIM, size=13)),
        height=260,
    )

    max_wind    = df["wind_speed_max_mph"].max()
    avg_wind    = df["wind_speed_max_mph"].mean()
    max_gusts   = df["wind_gusts_max_mph"].max()
    windiest    = df.loc[df["wind_speed_max_mph"].idxmax(), "forecast_date"].strftime("%b %d")
    windy_days  = (df["wind_speed_max_mph"] >= 35).sum()

    return html.Div([
        html.Div([
            kpi("Max Wind Speed", f"{max_wind:.1f} mph", YELLOW if max_wind >= 35 else ACCENT, f"on {windiest}"),
            kpi("Avg Wind Speed", f"{avg_wind:.1f} mph", ACCENT),
            kpi("Max Gusts",      f"{max_gusts:.1f} mph", ACCENT2),
            kpi("High Wind Days", str(windy_days), RED if windy_days > 0 else GREEN),
        ], style=dict(display="flex", gap="12px", marginBottom="20px", flexWrap="wrap")),
        card(dcc.Graph(figure=fig1, config=dict(displayModeBar=False))),
        card(dcc.Graph(figure=fig2, config=dict(displayModeBar=False))),
    ])


# ─────────────────────────────────────────────
# PAGE 5 — SEVERE WEATHER
# ─────────────────────────────────────────────

def render_severe_weather(df, alerts_df):
    alert_type_colors = {
        "freeze": ACCENT,
        "heat":   ACCENT2,
        "precip": PURPLE,
        "wind":   YELLOW,
    }

    if alerts_df.empty:
        no_alert = html.Div([
            html.Div("◈", style=dict(fontSize="48px", color=GREEN, textAlign="center", marginBottom="12px")),
            html.Div("NO SEVERE WEATHER ALERTS", style=dict(
                color=GREEN, fontSize="18px", textAlign="center",
                fontFamily="'Syne', sans-serif", letterSpacing="3px",
            )),
            html.Div("All forecast days are within safe thresholds.",
                     style=dict(color=TEXT_DIM, textAlign="center", marginTop="8px")),
        ], style=dict(padding="60px"))

        freeze_ct = heat_ct = precip_ct = wind_ct = 0
        alerts_table = no_alert
    else:
        freeze_ct = len(alerts_df[alerts_df["alert_type"] == "freeze"])
        heat_ct   = len(alerts_df[alerts_df["alert_type"] == "heat"])
        precip_ct = len(alerts_df[alerts_df["alert_type"] == "precip"])
        wind_ct   = len(alerts_df[alerts_df["alert_type"] == "wind"])

        # Alert timeline
        fig_alerts = go.Figure()
        for atype, color in alert_type_colors.items():
            sub = alerts_df[alerts_df["alert_type"] == atype]
            if not sub.empty:
                fig_alerts.add_trace(go.Scatter(
                    x=sub["alert_date"],
                    y=[atype.upper()] * len(sub),
                    mode="markers",
                    marker=dict(size=18, color=color, symbol="square"),
                    name=atype.capitalize(),
                    text=sub["alert_label"],
                    hovertemplate="%{text}<br>%{x}<extra></extra>",
                ))
        fig_alerts.update_layout(**PLOT_LAYOUT,
            title=dict(text="Severe Weather Alert Timeline", font=dict(color=TEXT_DIM, size=13)),
            height=280,
            yaxis=dict(gridcolor="#1e3a5f", categoryorder="array",
                       categoryarray=["FREEZE", "HEAT", "PRECIP", "WIND"]),
        )

        # Alert table
        table_rows = []
        for _, row in alerts_df.iterrows():
            color = alert_type_colors.get(row["alert_type"], ACCENT)
            table_rows.append(html.Tr([
                html.Td(row["alert_date"].strftime("%b %d"), style=dict(padding="10px 14px", color=TEXT_DIM)),
                html.Td(html.Span(row["alert_label"],
                    style=dict(background=f"{color}22", color=color, padding="3px 10px",
                               borderRadius="4px", fontSize="11px", letterSpacing="1px")),
                    style=dict(padding="10px 14px")),
                html.Td(f"{row['triggered_value']:.1f} {row['unit']}",
                    style=dict(padding="10px 14px", color=color, fontWeight="bold")),
                html.Td(f"Threshold: {row['threshold_value']:.1f} {row['unit']}",
                    style=dict(padding="10px 14px", color=TEXT_DIM, fontSize="11px")),
            ], style=dict(borderBottom=f"1px solid {BORDER}")))

        alerts_table = html.Div([
            dcc.Graph(figure=fig_alerts, config=dict(displayModeBar=False)),
            html.Div(style=dict(height="16px")),
            html.Div("TRIGGERED ALERTS", style=dict(color=TEXT_DIM, fontSize="11px",
                                                     letterSpacing="2px", marginBottom="12px")),
            html.Table([
                html.Thead(html.Tr([
                    html.Th("Date",      style=dict(padding="10px 14px", color=TEXT_DIM, textAlign="left", fontSize="11px", letterSpacing="1px")),
                    html.Th("Alert",     style=dict(padding="10px 14px", color=TEXT_DIM, textAlign="left", fontSize="11px", letterSpacing="1px")),
                    html.Th("Measured",  style=dict(padding="10px 14px", color=TEXT_DIM, textAlign="left", fontSize="11px", letterSpacing="1px")),
                    html.Th("Threshold", style=dict(padding="10px 14px", color=TEXT_DIM, textAlign="left", fontSize="11px", letterSpacing="1px")),
                ], style=dict(borderBottom=f"2px solid {BORDER}"))),
                html.Tbody(table_rows),
            ], style=dict(width="100%", borderCollapse="collapse")),
        ])

    return html.Div([
        html.Div([
            kpi("Freeze Alerts", str(freeze_ct), ACCENT  if freeze_ct > 0 else TEXT_DIM),
            kpi("Heat Alerts",   str(heat_ct),   ACCENT2 if heat_ct   > 0 else TEXT_DIM),
            kpi("Precip Alerts", str(precip_ct), PURPLE  if precip_ct > 0 else TEXT_DIM),
            kpi("Wind Alerts",   str(wind_ct),   YELLOW  if wind_ct   > 0 else TEXT_DIM),
            kpi("Total Alerts",  str(freeze_ct + heat_ct + precip_ct + wind_ct),
                RED if (freeze_ct + heat_ct + precip_ct + wind_ct) > 0 else GREEN),
        ], style=dict(display="flex", gap="12px", marginBottom="20px", flexWrap="wrap")),
        card(alerts_table),
    ])


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  Cincinnati Weather Dashboard")
    print("  Open: http://127.0.0.1:8050")
    print("=" * 50)
    app.run(debug=False)
