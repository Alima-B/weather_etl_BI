"""
Page Streamlit — Alertes & Conditions Météo Extrêmes
Intégration dans une app multi-pages : pages/alertes.py

Modifier les règles et intervalles de temps pour détection alerte
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pymongo import MongoClient
import numpy as np
import json
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
from config.settings import Settings, get_settings
from storage.mongodb_storage import MongoDBStorage
from config.towns import FRENCH_TOWNS
from BI.data_loader import load_hourly_data
from BI.helpers_BI import weather_condition_details,get_aqi_color,get_aqi_label,get_temp_color

###############################


# ============================================================
# HELPERS
# ============================================================

# english to french
dicoEN_FR = {"thunderstorm" : "Orage",
        "drizzle" : "Bruine",
        "rain" : "Pluie",
        "snow" : "Neige",
        "mist" : "Brume",
        "smoke" : "Fumée",
        "haze" : "Brume",
        "dust" : "Poussière",
        "fog" : "Brouillard",
        "clouds" : "Nuageux",
        "clear" : "Dégagé",
        "safe" : "sûre",
        "caution" : "Inconfort",
        "extreme caution" : "Extrême inconfort",
        "extreme danger" : "Danger extrême",
        "low" : "bas",
        "moderate" : "modéré",
        "high" : "haut",
        "very_high" : "très haut",
        "good" : "bon"
        }


###############################
# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION DES SEUILS ET CONSTANTES
# ──────────────────────────────────────────────────────────────────────────────
DELTA_THRESHOLDS = {
    "temperature_celsius": 3.0,   # °C/heure — variation brutale
    "wind_speed_mps":      4.0,   # m/s/heure — rafale soudaine
    "humidity_percent":    20.0,  # %/heure   — changement rapide
}

DELTA_LABELS = {
    "temperature_celsius": ("🌡️", "Température", "°C/h"),
    "wind_speed_mps":      ("💨", "Vent",         "m/s/h"),
    "humidity_percent":    ("💧", "Humidité",     "%/h"),
}

ALERT_KEYWORDS = ["heavy", "extreme", "orage", "storm", "tornado", "hurricane", "violent"]

ALERT_LEVELS   = {"moderate", "severe", "extreme"}

LEVEL_CONFIG = {
    "comfortable": {"color": "#22c55e", "bg": "#f0fdf4", "emoji": "✅", "label": "Confortable"},
    "moderate":    {"color": "#f59e0b", "bg": "#fffbeb", "emoji": "⚠️", "label": "Modéré"},
    "severe":      {"color": "#ef4444", "bg": "#fef2f2", "emoji": "🔴", "label": "Sévère"},
    "extreme":     {"color": "#7c3aed", "bg": "#f5f3ff", "emoji": "🚨", "label": "Extrême"},
}

LEVEL_ORDER = ["comfortable", "moderate", "severe", "extreme"]

CHART_COLORS = {
    "temperature_celsius": "#f97316",
    "wind_speed_mps":      "#3b82f6",
    "humidity_percent":    "#06b6d4",
}

# ──────────────────────────────────────────────────────────────────────────────
# LOGIQUE DE DÉTECTION DES ALERTES
# ──────────────────────────────────────────────────────────────────────────────

def detect_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Analyse le dataframe et retourne un DataFrame d'alertes avec les colonnes :
    hour, hour_formatted, type, category, message, severity
    """
    alerts = []
    df = df.copy().reset_index(drop=True)

    # ── 1. Deltas entre mesures consécutives ──────────────────────────────────
    for col, threshold in DELTA_THRESHOLDS.items():
        if col not in df.columns:
            continue
        icon, label, unit = DELTA_LABELS[col]
        deltas = df[col].diff().abs()
        flagged = df[deltas > threshold]
        for idx, row in flagged.iterrows():
            delta_val = deltas.loc[idx]
            alerts.append({
                "hour":           row.get("hour", idx),
                "hour_formatted": row.get("hour_formatted", f"H+{idx}"),
                "type":           "delta",
                "category":       label,
                "icon":           icon,
                "message":        (
                    f"Variation rapide de {label.lower()} : "
                    f"**+{delta_val:.1f} {unit}** "
                    f"(seuil : {threshold} {unit})"
                ),
                "severity":       "moderate",
                "details":        [],
            })

    # ── 2. Mots-clés dans weather_description ────────────────────────────────
    if "weather_description" in df.columns:
        for idx, row in df.iterrows():
            desc = str(row.get("weather_description", "")).lower()
            found = [kw for kw in ALERT_KEYWORDS if kw in desc]
            if found:
                alerts.append({
                    "hour":           row.get("hour", idx),
                    "hour_formatted": row.get("hour_formatted", f"H+{idx}"),
                    "type":           "description",
                    "category":       "Phénomène météo",
                    "icon":           "⛈️",
                    "message":        (
                        f"Conditions critiques détectées : "
                        f"**{row['weather_description']}** "
                        f"(mot-clé : {', '.join(found)})"
                    ),
                    "severity":       "severe",
                    "details":        [],
                })

    # ── 3. Niveau de sévérité (level / details) ───────────────────────────────
    if "level" in df.columns:
        for idx, row in df.iterrows():
            lvl = str(row.get("level", "")).lower()
            if lvl in ALERT_LEVELS:
                raw_details = row.get("details", [])
                # Sécurisation : details peut être une liste ou une string
                if isinstance(raw_details, str):
                    try:
                        import ast
                        raw_details = ast.literal_eval(raw_details)
                    except Exception:
                        raw_details = [raw_details]
                details_str = ", ".join(raw_details) if raw_details else ""
                alerts.append({
                    "hour":           row.get("hour", idx),
                    "hour_formatted": row.get("hour_formatted", f"H+{idx}"),
                    "type":           "level",
                    "category":       "Sévérité globale",
                    "icon":           LEVEL_CONFIG.get(lvl, {}).get("emoji", "⚠️"),
                    "message":        (
                        f"Niveau **{LEVEL_CONFIG.get(lvl, {}).get('label', lvl)}** — "
                        f"{details_str}"
                    ),
                    "severity":       lvl,
                    "details":        raw_details,
                })

    if not alerts:
        return pd.DataFrame()

    alerts_df = pd.DataFrame(alerts).sort_values("hour").reset_index(drop=True)
    return alerts_df


def worst_level(alerts_df: pd.DataFrame) -> str:
    """Retourne le niveau de sévérité le plus élevé trouvé dans les alertes."""
    if alerts_df.empty:
        return "comfortable"
    for lvl in reversed(LEVEL_ORDER):
        if (alerts_df["severity"] == lvl).any():
            return lvl
    return "comfortable"


def next_alert_hour(alerts_df: pd.DataFrame, current_hour: int = 0) -> dict | None:
    """Retourne la prochaine alerte à partir de l'heure courante."""
    future = alerts_df[alerts_df["hour"] > current_hour]
    if future.empty:
        return None
    return future.iloc[0].to_dict()


# ──────────────────────────────────────────────────────────────────────────────
# GRAPHIQUES PLOTLY
# ──────────────────────────────────────────────────────────────────────────────

def _add_alert_bands(fig, alerts_df, col_name, df, row, col=1):
    """Ajoute des zones colorées sur le graphique aux heures d'alerte."""
    if alerts_df.empty:
        return
    alerted_hours = set(alerts_df["hour"].tolist())
    yvals = df[col_name].dropna()
    if yvals.empty:
        return
    y_min = yvals.min() - abs(yvals.min()) * 0.05
    y_max = yvals.max() + abs(yvals.max()) * 0.05

    for h in alerted_hours:
        row_data = alerts_df[alerts_df["hour"] == h].iloc[0]
        lvl = row_data["severity"]
        color = LEVEL_CONFIG.get(lvl, LEVEL_CONFIG["moderate"])["color"]
        fig.add_vrect(
            x0=h - 0.4, x1=h + 0.4,
            fillcolor=color, opacity=0.15,
            layer="below", line_width=0,
            row=row, col=col,
        )


def build_charts(df: pd.DataFrame, alerts_df: pd.DataFrame) -> go.Figure:
    """Construit un graphique multi-lignes annoté avec les zones d'alerte."""

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "🌡️ Température ressentie (°C)",
            "💨 Vitesse du vent (m/s)",
            "💧 Humidité (%)",
        ],
        vertical_spacing=0.08,
    )

    x = df["hour"].tolist()
    x_labels = df["hour_formatted"].tolist() if "hour_formatted" in df.columns else x

    # ── Température ──────────────────────────────────────────────────────────
    if "temperature_celsius" in df.columns:
        _add_alert_bands(fig, alerts_df[alerts_df["category"] == "Température"] if not alerts_df.empty else alerts_df,
                         "temperature_celsius", df, row=1)
        fig.add_trace(go.Scatter(
            x=x, y=df["temperature_celsius"],
            name="Température",
            mode="lines+markers",
            line=dict(color=CHART_COLORS["temperature_celsius"], width=2.5),
            marker=dict(size=5),
            hovertemplate="H+%{x}h — %{y:.1f}°C<extra></extra>",
        ), row=1, col=1)

        if "feels_like_celsius" in df.columns:
            fig.add_trace(go.Scatter(
                x=x, y=df["feels_like_celsius"],
                name="Ressenti",
                mode="lines",
                line=dict(color="#fbbf24", width=1.5, dash="dot"),
                hovertemplate="H+%{x}h — Ressenti %{y:.1f}°C<extra></extra>",
            ), row=1, col=1)

    # ── Vent ─────────────────────────────────────────────────────────────────
    if "wind_speed_mps" in df.columns:
        _add_alert_bands(fig, alerts_df[alerts_df["category"] == "Vent"] if not alerts_df.empty else alerts_df,
                         "wind_speed_mps", df, row=2)
        fig.add_trace(go.Scatter(
            x=x, y=df["wind_speed_mps"],
            name="Vent moyen",
            mode="lines+markers",
            line=dict(color=CHART_COLORS["wind_speed_mps"], width=2.5),
            marker=dict(size=5),
            hovertemplate="H+%{x}h — %{y:.1f} m/s<extra></extra>",
        ), row=2, col=1)

        if "wind_gust_mps" in df.columns:
            fig.add_trace(go.Scatter(
                x=x, y=df["wind_gust_mps"],
                name="Rafales",
                mode="lines",
                line=dict(color="#93c5fd", width=1.5, dash="dash"),
                hovertemplate="H+%{x}h — Rafales %{y:.1f} m/s<extra></extra>",
            ), row=2, col=1)

    # ── Humidité ─────────────────────────────────────────────────────────────
    if "humidity_percent" in df.columns:
        _add_alert_bands(fig, alerts_df[alerts_df["category"] == "Humidité"] if not alerts_df.empty else alerts_df,
                         "humidity_percent", df, row=3)
        fig.add_trace(go.Scatter(
            x=x, y=df["humidity_percent"],
            name="Humidité",
            mode="lines+markers",
            line=dict(color=CHART_COLORS["humidity_percent"], width=2.5),
            marker=dict(size=5),
            fill="tozeroy",
            fillcolor="rgba(6,182,212,0.07)",
            hovertemplate="H+%{x}h — %{y:.0f}%<extra></extra>",
        ), row=3, col=1)

    # ── Annotations sur toutes les heures d'alerte ───────────────────────────
    if not alerts_df.empty:
        for _, alert in alerts_df.drop_duplicates("hour").iterrows():
            h = alert["hour"]
            lvl = alert["severity"]
            color = LEVEL_CONFIG.get(lvl, LEVEL_CONFIG["moderate"])["color"]
            for row_idx, col_name in enumerate(
                ["temperature_celsius", "wind_speed_mps", "humidity_percent"], start=1
            ):
                if col_name in df.columns:
                    y_val = df.loc[df["hour"] == h, col_name]
                    if not y_val.empty:
                        fig.add_annotation(
                            x=h,
                            y=y_val.values[0],
                            text=alert["icon"],
                            showarrow=False,
                            font=dict(size=14),
                            row=row_idx, col=1,
                        )

    # ── Mise en forme globale ─────────────────────────────────────────────────
    fig.update_layout(
        height=620,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=12),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
        ),
        margin=dict(l=10, r=10, t=60, b=10),
        hovermode="x unified",
    )

    fig.update_xaxes(
        tickmode="array",
        tickvals=x[::3],
        ticktext=[x_labels[i] for i in range(0, len(x_labels), 3)],
        title_text="Heure locale (H+x)",
        row=3, col=1,
        gridcolor="rgba(150,150,150,0.15)",
    )
    fig.update_yaxes(gridcolor="rgba(150,150,150,0.15)")

    return fig


def build_severity_timeline(df: pd.DataFrame) -> go.Figure:
    """Heatmap horizontale du niveau de sévérité sur 48h."""
    if "level" not in df.columns:
        return None

    level_to_num = {lvl: i for i, lvl in enumerate(LEVEL_ORDER)}
    colorscale = [
        [0.00, LEVEL_CONFIG["comfortable"]["color"]],
        [0.33, LEVEL_CONFIG["moderate"]["color"]],
        [0.66, LEVEL_CONFIG["severe"]["color"]],
        [1.00, LEVEL_CONFIG["extreme"]["color"]],
    ]

    z = [[level_to_num.get(str(lvl).lower(), 0) for lvl in df["level"]]]
    x = df["hour_formatted"].tolist() if "hour_formatted" in df.columns else df["hour"].tolist()
    hover = [
        f"H+{row['hour']}h — {LEVEL_CONFIG.get(str(row.get('level','')).lower(), {}).get('label', row.get('level',''))}"
        for _, row in df.iterrows()
    ]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=x,
        colorscale=colorscale,
        zmin=0, zmax=3,
        showscale=False,
        hovertemplate="%{customdata}<extra></extra>",
        customdata=[hover],
        xgap=2,
    ))

    fig.update_layout(
        height=90,
        margin=dict(l=10, r=10, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showticklabels=False, showgrid=False),
        xaxis=dict(
            tickmode="array",
            tickvals=x[::6],
            ticktext=x[::6],
            gridcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# PAGE STREAMLIT PRINCIPALE
# ──────────────────────────────────────────────────────────────────────────────

def render_alerts_page(df: pd.DataFrame):
    """
    Fonction principale à appeler depuis votre app Streamlit.
    Exemple d'intégration :
        from weather_alerts import render_alerts_page
        render_alerts_page(st.session_state["forecast_df"])
    """

    st.title("🌩️ Alertes & Conditions Extrêmes")
    st.caption("Prévisions sur 48h — analyse des variations et seuils critiques")

    if df is None or df.empty:
        st.warning("Aucune donnée de prévision disponible.")
        return

    # ── Détection ─────────────────────────────────────────────────────────────
    alerts_df = detect_alerts(df)
    top_level  = worst_level(alerts_df)
    cfg        = LEVEL_CONFIG[top_level]
    n_alerts   = len(alerts_df)
    current_h  = df["hour"].min() if "hour" in df.columns else 0
    next_a     = next_alert_hour(alerts_df, current_h) if not alerts_df.empty else None

    # ── Bandeau d'état global ─────────────────────────────────────────────────
    banner_messages = {
        "comfortable": ("✅ Aucune condition extrême prévue sur 48h", "#f0fdf4", "#166534"),
        "moderate":    ("⚠️ Conditions modérées détectées — restez attentif", "#fffbeb", "#92400e"),
        "severe":      ("🔴 Conditions sévères prévues — prudence recommandée", "#fef2f2", "#991b1b"),
        "extreme":     ("🚨 ALERTE EXTRÊME — conditions dangereuses attendues", "#f5f3ff", "#4c1d95"),
    }
    msg, bg, fg = banner_messages[top_level]
    st.markdown(
        f"""<div style="
            background:{bg}; color:{fg};
            border-left: 5px solid {cfg['color']};
            border-radius: 8px; padding: 14px 20px;
            font-size: 1.05rem; font-weight: 600;
            margin-bottom: 1rem;">
            {msg}
        </div>""",
        unsafe_allow_html=True,
    )

    # ── 3 métriques ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="Pire niveau détecté",
            value=f"{cfg['emoji']} {cfg['label']}",
        )
    with col2:
        st.metric(
            label="Nombre d'alertes",
            value=str(n_alerts) if n_alerts else "Aucune",
        )
    with col3:
        if next_a:
            st.metric(
                label="Prochaine alerte",
                value=next_a.get("hour_formatted", f"H+{next_a['hour']}"),
                help=next_a.get("message", ""),
            )
        else:
            st.metric(label="Prochaine alerte", value="—")

    st.divider()

    # ── Timeline de sévérité ──────────────────────────────────────────────────
    if "level" in df.columns:
        st.subheader("Niveau de sévérité sur 48h")
        fig_timeline = build_severity_timeline(df)
        if fig_timeline:
            st.plotly_chart(fig_timeline, use_container_width=True, config={"displayModeBar": False})

        # Légende manuelle
        cols = st.columns(4)
        for i, lvl in enumerate(LEVEL_ORDER):
            c = LEVEL_CONFIG[lvl]
            cols[i].markdown(
                f"<span style='color:{c['color']};font-weight:700'>"
                f"{c['emoji']} {c['label']}</span>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Graphiques météo annotés ───────────────────────────────────────────────
    st.subheader("Évolution des variables sur 48h")

    # Filtre optionnel : afficher seulement les heures avec alertes
    show_all = st.toggle("Afficher toutes les heures (désactiver = zoom sur alertes)", value=True)

    df_plot = df
    if not show_all and not alerts_df.empty:
        alert_hours = alerts_df["hour"].unique()
        # Fenêtre ±3h autour de chaque alerte
        window_hours = set()
        for h in alert_hours:
            window_hours.update(range(max(0, h - 3), h + 4))
        df_plot = df[df["hour"].isin(window_hours)]

    fig_charts = build_charts(df_plot, alerts_df)
    st.plotly_chart(fig_charts, use_container_width=True)

    st.divider()

    # ── Liste des alertes détaillées ──────────────────────────────────────────
    st.subheader(f"Détail des alertes ({n_alerts})")

    if alerts_df.empty:
        st.success("Aucune alerte sur les 48 prochaines heures.")
    else:
        # Filtre par type
        type_labels = {"delta": "Variation rapide", "description": "Phénomène météo", "level": "Sévérité"}
        available_types = alerts_df["type"].unique().tolist()
        selected_types = st.multiselect(
            "Filtrer par catégorie",
            options=available_types,
            default=available_types,
            format_func=lambda t: type_labels.get(t, t),
        )
        filtered = alerts_df[alerts_df["type"].isin(selected_types)] if selected_types else alerts_df

        for _, alert in filtered.iterrows():
            lvl   = alert["severity"]
            c     = LEVEL_CONFIG.get(lvl, LEVEL_CONFIG["moderate"])
            hour_label = alert.get("hour_formatted", f"H+{alert['hour']}")

            with st.container():
                st.markdown(
                    f"""<div style="
                        background:{c['bg']};
                        border-left: 4px solid {c['color']};
                        border-radius: 6px;
                        padding: 10px 16px;
                        margin-bottom: 8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:700; color:{c['color']}">
                                {alert['icon']} {alert['category']}
                            </span>
                            <span style="
                                background:{c['color']}22;
                                color:{c['color']};
                                border-radius:12px;
                                padding:2px 10px;
                                font-size:0.85rem;
                                font-weight:600;">
                                {hour_label}
                            </span>
                        </div>
                        <div style="margin-top:4px; color:#374151; font-size:0.95rem">
                            {alert['message']}
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )

    st.divider()

    # ── Tableau récapitulatif (expander) ──────────────────────────────────────
    with st.expander("Voir toutes les données brutes"):
        cols_to_show = [c for c in [
            "hour_formatted", "temperature_celsius", "feels_like_celsius",
            "wind_speed_mps", "wind_gust_mps", "humidity_percent",
            "weather_description", "level", "details",
        ] if c in df.columns]
        st.dataframe(
            df[cols_to_show].rename(columns={
                "hour_formatted":       "Heure",
                "temperature_celsius":  "Temp (°C)",
                "feels_like_celsius":   "Ressenti (°C)",
                "wind_speed_mps":       "Vent (m/s)",
                "wind_gust_mps":        "Rafales (m/s)",
                "humidity_percent":     "Humidité (%)",
                "weather_description":  "Description",
                "level":                "Niveau",
                "details":              "Détails",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE STANDALONE (pour tester la page seule)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, ast

    st.set_page_config(
        page_title="Alertes météo",
        page_icon="🌩️",
        layout="wide",
    )

    # Données de démo — remplacez par votre vraie source
    @st.cache_data
    def load_demo_data():
        """Génère un dataframe de démo sur 48h avec quelques conditions extrêmes."""
        import numpy as np
        np.random.seed(42)
        n = 48
        hours = list(range(n))
        temp = 10 + np.cumsum(np.random.normal(0, 0.8, n))
        temp[12] += 8   # pic brutal
        temp[13] += 9   # continuation
        wind = np.abs(np.random.normal(4, 2, n))
        wind[20] = 22   # fort vent
        wind[21] = 18
        humidity = np.clip(80 + np.random.normal(0, 10, n), 20, 100)
        humidity[30] = 98
        humidity[31] = 45  # chute brutale

        descriptions = ["light rain"] * n
        descriptions[15] = "heavy rain"
        descriptions[16] = "heavy thunderstorm"

        levels = ["comfortable"] * n
        levels[12] = "moderate"
        levels[13] = "severe"
        levels[20] = "extreme"
        levels[30] = "moderate"

        details_list = [[]] * n
        details_list[12] = ["température inconfortable", "forte humidité"]
        details_list[13] = ["température extrême", "très forte humidité"]
        details_list[20] = ["vent violent", "température inconfortable"]
        details_list[30] = ["très forte humidité"]

        df = pd.DataFrame({
            "hour":                hours,
            "hour_formatted":      [f"{h:02d}:00" for h in hours],
            "temperature_celsius": temp.round(2),
            "feels_like_celsius":  (temp - 1.5).round(2),
            "wind_speed_mps":      wind.round(2),
            "wind_gust_mps":       (wind * 1.4).round(2),
            "humidity_percent":    humidity.round(0).astype(int),
            "weather_description": descriptions,
            "level":               levels,
            "details":             details_list,
        })
        return df


##TEST
    date_forecast = st.date_input("Sélectionnez une date (aujourd'hui par défaut)", value = 'today'
                             ,format = "DD-MM-YYYY",key = "map_date")
    # charge les données de prévisions
    city_forecasts = city_forecasts = load_hourly_data("gold_weather_daily",forecast=True
                    ,date = date_forecast.isoformat(),date_end=None, date_start=None, city = "paris")
    city_forecasts["date"] = (
                    pd.to_datetime(city_forecasts["timestamp_utc"])
                    .dt.tz_convert("Europe/Paris")
                    .dt.strftime("%Y-%m-%d")
                )
    
    weather_cdt = city_forecasts.apply(
                lambda row : weather_condition_details(
                    feels_like = row["feels_like_celsius"],
                    humidity= row["humidity_percent"],
                    wind_speed= row["wind_speed_mps"],
                    wind_gust= row["wind_gust_mps"],
                    uvi = row["uvi"],
                ), axis = 1)
    
    df_weather_cdt = pd.DataFrame(weather_cdt.tolist())
    city_forecasts = pd.concat([city_forecasts, df_weather_cdt], axis=1)
    
    # demo_df = load_demo_data()
    render_alerts_page(city_forecasts)