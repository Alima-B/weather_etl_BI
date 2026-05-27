"""V2 modifie la pip d'aggregation de poll et weather"""

# comparer les perf si  filtre tout avec python ou si avec mongo db. (surtout pour les requetes où peut y avoir bcp de données retournée)
# class par page
# class pour load les datas


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

from BI.helpers_BI import get_aqi_color,get_aqi_label,get_temp_color,trend_icon,advisory_html,weather_condition_details
from BI.data_loader import load_hourly_period,load_hourly_data,load_agg_data,_build_pipeline_agg,_build_hour_filter,local_date_to_utc_bounds
# from BI.page_map import render_map_page
# from BI.Alerte_page import render_alerts_page

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="🌍 AirMonitor France",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
    .main-header {
        font-size: 1.9rem; font-weight: 700; color: #1a1a2e;
        border-left: 5px solid #4361ee; padding-left: 14px;
        margin-bottom: 0.5rem;
    }
    .sub-header { color: #555; font-size: 0.95rem; margin-bottom: 1.5rem; }
    .kpi-box {
        background: linear-gradient(135deg, #4361ee, #3a0ca3);
        border-radius: 14px; padding: 1rem 1.2rem; color: white; text-align: center;
    }
    .kpi-box-green  { background: linear-gradient(135deg, #06d6a0, #028090); border-radius: 14px; padding: 1rem 1.2rem; color: white; text-align: center; }
    .kpi-box-orange { background: linear-gradient(135deg, #f77f00, #d62828); border-radius: 14px; padding: 1rem 1.2rem; color: white; text-align: center; }
    .kpi-box-red    { background: linear-gradient(135deg, #d62828, #6a0572); border-radius: 14px; padding: 1rem 1.2rem; color: white; text-align: center; }
    .kpi-val { font-size: 2rem; font-weight: 700; }
    .kpi-lbl { font-size: 0.78rem; opacity: 0.85; margin-top: 2px; }
    .advisory-ok     { background:#d4edda; border-left:5px solid #28a745; border-radius:10px; padding:1rem; color:#155724; margin:0.8rem 0; }
    .advisory-warn   { background:#fff3cd; border-left:5px solid #ffc107; border-radius:10px; padding:1rem; color:#856404; margin:0.8rem 0; }
    .advisory-danger { background:#f8d7da; border-left:5px solid #dc3545; border-radius:10px; padding:1rem; color:#721c24; margin:0.8rem 0; }
    .alert-row { border-radius:10px; padding:0.7rem 1rem; margin:0.4rem 0; display:flex; align-items:center; gap:12px; }
    .alert-critical { background:#fde8e8; border-left:4px solid #dc3545; }
    .alert-high     { background:#fff4e6; border-left:4px solid #f77f00; }
    .corr-bar { height:8px; border-radius:4px; margin-top:4px; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# STATIC REFERENCE DATA /DATABASE CONNECTION
# ============================================================
# settings: Optional[Settings] = None
# settings = settings or get_settings()
# mongodb = MongoDBStorage(settings)

# @st.cache_resource
# def get_db() :
#     '''Connection the mongobase database'''
#     uri = mongodb._build_connection_uri()
#     client = MongoClient(uri)
#     return client["weather_etl"]

CITIES_COORDS = {
    town.name: {"lat": town.lat, "lon": town.lon}
    for town in FRENCH_TOWNS
}


# ============================================================
# LOAD DATAS
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

        
# ============================================================
# SIDE BAR
# ============================================================
with st.sidebar:
    st.markdown("## Surveillance Qualité de l'Air & Météo")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["🗺️  Carte Interactive", "📊  KPI & Pollution", "🚨  Alertes & Prévisions", "   Corrélations"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    city = st.selectbox("Ville",sorted(CITIES_COORDS.keys()))
    today_date = st.date_input("Date d'aujourd'hui", value = 'today',format = "DD.MM.YYYY")
    date_range = st.date_input("Période",value=["today", datetime(2026, 12, 31)],format = "DD/MM/YYYY")
    
    
    st.markdown("---")
## mettre des tabs pour météo du jour résumé ou météo par heure? avec changement de la selectbox au changemen de tab
if page == "🗺️  Carte Interactive":
    st.markdown('<div class="main-header">🗺️ Carte Météo & Qualité de l\'Air</div>', unsafe_allow_html=True)

    sel_date = st.date_input("Sélectionnez une date (aujourd'hui par défaut)", value = 'today'
                             ,format = "DD-MM-YYYY",key = "map_date")

    st.markdown(f'<div class="sub-header">Données du <b>{sel_date}</b>.  Survolez une ville pour tous les détails</div>', unsafe_allow_html=True)
    
    
    # df_date = load_daily(date=today_date.isoformat())
    df_agg  = load_agg_data(date=sel_date.isoformat())
    
    # charge df avec données horaire
    df_air  = load_hourly_data("gold_air_quality_daily",forecast = False, date = sel_date.isoformat(),date_end=None,date_start=None)
    df_meteo = load_hourly_data("gold_weather_daily",forecast = False ,date = sel_date.isoformat(),date_end=None, date_start=None)
    data_heure = load_hourly_period(date = sel_date.isoformat(),city=None)
    
    # Helpers (handles NA)
    def g(r, col, default=None):
        val = r.get(col, default)
        return default if (val is None or (isinstance(val, float) and pd.isna(val))) else val

    def fmt(val, spec, fallback="N/A"):
        return format(val, spec) if val is not None else fallback

    # Tabs : daily, hourly data
    tab_daily, tab_hourly = st.tabs(["📅 Résumé Journée", "🕐 Météo horaire"])


    def hover_hourly(r):
                return (
                    f"<b>📍 {str.capitalize(g(r, 'city', '?'))}</b> — "
                    f"<b>{g(r, 'hour_formatted', '?')}</b><br>"
                    f"─────────────────<br>"
                    f"🌡️ Temp : <b>{fmt(g(r,'temperature'), '.1f')}°C "
                            f"(ressentie {fmt(g(r,'feels_like'), '.1f')}°C)</b><br>"
                    f"💧 Humidité : <b>{fmt(g(r,'humidity'), '.0f')}%</b><br>"
                    f"⏲ Pression : <b>{fmt(g(r,'pressure_hpa'), '.0f')}hPa</b><br>"
                    f"💨 Vent : <b>{fmt(g(r,'wind_speed'), '.1f')} m/s "
                            f"({g(r,'wind_direction_cardinal','?')})</b><br>"
                    f"💨 Rafales : <b>{fmt(g(r,'wind_gust_mps'), '.1f')} m/s</b><br>"
                    f"☀️ UVI : <b>{fmt(g(r,'uvi'), '.1f')} ({dicoEN_FR.get(g(r,'uvi_category','?'))})</b><br>"
                    f"⛅ Météo : <b>{dicoEN_FR.get((g(r,'weather','?')))}</b><br>"
                    f"⚠️ Alerte chaleur : <b>{dicoEN_FR.get(g(r,'heat_index_warning','Aucune'))}</b><br>"
                    f"─────────────────<br>"
                    f"🏭 AQI : <b>{fmt(g(r,'aqi'), '.0f')}</b> ({get_aqi_label(g(r,'aqi',"N/A"))})<br>"
                    f"🔵 PM2.5 : <b>{fmt(g(r,'pm25'), '.1f')}</b><br>"
                    f"🟡 PM10 : <b>{fmt(g(r,'pm10'), '.1f')}</b><br>"
                    f"🔴 NO₂ : <b>{fmt(g(r,'no2'), '.1f')}</b><br>"
                    f"🟢 O₃ : <b>{fmt(g(r,'o3'), '.1f')}</b><br>"
                    f"Polluant Dom. : <b>{g(r,'primary_pollutant','N/A')}</b><br>"
                    f"─────────────────<br>"
                )
    
    def hover_dayly(r):
                    return (
                        f"<b>📍 {str.capitalize(g(r, 'city', '?'))}</b><br>"
                    f"─────────────────<br>"
                    f"🌡️ Temp : <b>{fmt(g(r,'w_avg_temperature'), '.1f')}°C "
                    f"(ressentie {fmt(g(r,'w_avg_feels_like'), '.1f')}°C)</b><br>"
                    f"🌡️ Min/Max : <b>{fmt(g(r,'w_min_temperature'), '.1f')}° / {fmt(g(r,'w_max_temperature'), '.1f')}°</b><br> "
                    f"💧 Humidité : <b>{fmt(g(r,'w_avg_humidity'), '.0f')}%</b><br>"
                    f"⏲ Pression : <b>{fmt(g(r,'w_avg_pressure'), '.0f')}hPa</b><br>"
                    f"💨 Vent Max : <b>{fmt(g(r,'w_max_wind_speed'), '.1f')} m/s</b><br>"
                    f"🌧️ Précip. : <b>{'Oui' if g(r,'w_precipitation_detected') else 'Non'}</b><br>"
                    f"☁️ Couverture Nuageuse : <b>{fmt(g(r,'w_avg_cloud_coverage'), '.1f')}%</b><br>"
                    f"☀️ UVI Max : <b>{fmt(g(r,'w_max_uvi'), '.1f')}</b><br>"
                    
                    f"─────────────────<br>"
                    f"🏭 AQI : <b>{fmt(g(r,'pol_avg_aqi'), '.0f')}</b>  ({get_aqi_label(g(r,'pol_avg_aqi'))})<br>"
                    f"🔵 PM2.5 : <b>{fmt(g(r,'pol_avg_pm25'), '.1f')}</b><br>"
                    f"🟡 PM10 : <b>{fmt(g(r,'pol_avg_pm10'), '.1f')}</b><br>"
                    f"🔴 NO₂ : <b>{fmt(g(r,'pol_avg_no2'), '.1f')}</b><br>"
                    f"🟢 O₃ : <b>{fmt(g(r,'pol_avg_o3'), '.1f')}</b><br>"
                    f"─────────────────<br>"
                    f"⛅ Condition météo : <b>{dicoEN_FR.get(g(r,'w_dominant_weather_condition'),"N/A")}</b><br>"
                    f"🌡️ Tendance T° : <b>{trend_icon(g(r,'w_temp_trend'))}</b><br>"
                    f"📈 Tendance AQI : <b>{trend_icon(g(r,'pol_aqi_trend'))}</b>"
                    )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — Carte journalière 
    # ════════════════════════════════════════════════════════════════════════
    ## Modifier pour avoir une seule page :
    # un bouton pour avoir les données par jour ou par heure. Afficher les deux type de cartes en focntion du choix
    # pour le hover faire 2 fct (comme tab horaire)
    # Graphique pour chaque KPI
    
    with tab_daily:
        mode = st.radio("Carte journalière ou horaire",
                        options = ["Résumé horaire","Météo horaire"],
                        horizontal = True)
        col_map, col_ctrl = st.columns([3, 1])

        with col_ctrl:
            map_style = st.selectbox("Style carte", ["carto-positron", "open-street-map"], key="style_daily")
            # size_by   = st.selectbox("Taille des points", ["AQI", "Température"], key="size_daily")
            color_by  = st.selectbox("Couleur", ["AQI (norme)", "Température"], key="color_daily")
            if color_by == "AQI (norme)":
                st.markdown("##### Échelle AQI")
                for rng, lbl, col in [
                    ("0–50",    "Bon",               "#00c853"),
                    ("51–100",  "Modéré",            "#f9a825"),
                    ("101–150", "Mauvais (sensibles)","#ef6c00"),
                    ("151–200", "Mauvais",            "#c62828"),
                    ("201-300", "Très mauvais",       "#6a1b9a"),
                    (">300",    "Dangereux",          "#6f0909"),
                    ("No data","","#BEBABA")
                ]:
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
                        f'<div style="width:16px;height:16px;border-radius:50%;background:{col}"></div>'
                        f'<span style="font-size:0.78rem"><b>{rng}</b> {lbl}</span></div>',
                        unsafe_allow_html=True
                    )
            else :   
                st.markdown("##### Échelle Témpérature")
                for rng, lbl, col in [
                    ("< -15",    "Froid Extrême", "#4A148C"),
                    ("-15–-5",  "Grand Froid", "#1565C0"),
                    ("-5-0", "Gel","#42A5F5"),
                    ("0-7", "Frais",   "#81C784"),
                    ("7-14", "Douceur", "#CDDC39"),
                    ("14-20", "Agréable", "#FFEB3B"),
                    ("20-25", "Chaud", "#FBC02D"),
                    ("25-30", "Très Chaud", "#FB8C00"),
                    ("30-35", "Forte Chaleur",  "#E53935"),
                    (">35",    "Chaleur Extrême", "#B71C1C"),
                    ("No data","","#BEBABA")
                ]:
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
                        f'<div style="width:16px;height:16px;border-radius:50%;background:{col}"></div>'
                        f'<span style="font-size:0.78rem"><b>{rng}</b> {lbl}</span></div>',
                        unsafe_allow_html=True
                    )    
            
            
        if mode == "Résumé horaire" : 
            choosen_df = df_agg
        else : 
            choosen_df = data_heure
            
        if choosen_df.empty:
            st.info(f"Pas de données pour la date {sel_date}")
        else : 
            choosen_df["hover"] = choosen_df.apply(hover_dayly, axis=1)
                        
        # size_key = {"AQI": "pol_avg_aqi", "PM2.5": "pol_avg_pm25", "Vent": "w_avg_wind_speed"}[size_by]
        # df_agg["marker_size"] = (df_agg[size_key] - df_agg[size_key].min()) / (df_agg[size_key].max() - df_agg[size_key].min() + 1) * 30 + 20

            # if color_by == "AQI (norme)":
            #     choosen_df["marker_color"] = choosen_df["pol_avg_aqi"].apply(get_aqi_color)
            #     # use_colorscale = False
            # elif color_by == "Température":
            #     choosen_df["marker_color"] = choosen_df["w_avg_feels_like"].apply(get_temp_color)
            #     # use_colorscale = True

            fig_map = go.Figure()
            for _, row in choosen_df.iterrows():
                # mc = row["marker_color"] if not use_colorscale else get_aqi_color(row["pol_avg_aqi"])
                # mc = row["marker_color"]
                mc = get_aqi_color(row["pol_avg_aqi"]) if color_by == "AQI (norme)" else get_temp_color(row["w_avg_temperature"])
                fig_map.add_trace(go.Scattermapbox(
                    lat=[CITIES_COORDS[row["city"]].get("lat")], 
                    lon=[CITIES_COORDS[row["city"]].get("lon")],
                    mode="markers+text",
                    # marker=dict(size=row["marker_size"], color=mc, opacity=0.85),
                    marker=dict(size=25, color=mc, opacity=0.85),
                    text=[row["city"]], textposition="top center",
                    textfont=dict(size=11, color="#1a1a2e", family="Inter"),
                    hovertext=row["hover"], hoverinfo="text",
                    showlegend=False,
                ))
                fig_map.add_trace(go.Scattermapbox(
                    lat=[CITIES_COORDS[row["city"]].get("lat")], lon=[CITIES_COORDS[row["city"]].get("lon")],
                    mode="text",
                    text=[f"{row['pol_avg_aqi']:.0f}"],
                    textfont=dict(size=10, color="white", family="Inter"),
                    hoverinfo="skip", showlegend=False,
                ))

            fig_map.update_layout(
                mapbox=dict(style=map_style, center=dict(lat=46.6, lon=2.5), zoom=4.6),
                margin=dict(l=0, r=0, t=0, b=0), height=560,
            )
            with col_map:
                st.plotly_chart(fig_map, width='stretch')

            st.markdown("---")
            st.markdown(f"### Tableau de synthèse : {sel_date}")
            
            df_show = choosen_df[[
                "city","pol_avg_aqi","pol_max_alert_level","pol_aqi_trend",
                "pol_avg_pm25","pol_avg_pm10","pol_avg_no2","pol_avg_o3",
                "w_avg_temperature","w_temp_trend","w_avg_humidity","w_avg_pressure","w_avg_wind_speed","w_dominant_weather_condition"
                ]].copy()
            df_show.columns = ["Ville","AQI","Alerte pollution","Tendance","PM2.5","PM10","NO₂","O3"
                            ,"Temp °C","Tendance T°","Humidité %","Pression","Vent m/s","Condition météo"]
            df_show["Alerte pollution"] = df_show["AQI"].apply(get_aqi_label) 
            df_show["Tendance"] = df_show["Tendance"].map({"rising":"📈 Hausse","falling":"📉 Baisse","stable":"➡️ Stable"})
            df_show["Tendance T°"] = df_show["Tendance T°"].map({"rising":"📈 Hausse","falling":"📉 Baisse","stable":"➡️ Stable"})
            df_show["Condition météo"] = df_show["Condition météo"].map(dicoEN_FR)
            df_show["Alerte météo"] = choosen_df.apply(
                lambda row : weather_condition_details(
                    feels_like = row["w_avg_feels_like"],
                    humidity= row["w_avg_humidity"],
                    wind_speed= row["w_avg_wind_speed"],
                    wind_gust= row["w_max_wind_gust"],
                    uvi = row["w_avg_uvi"],
                )["details"], axis = 1)
            st.dataframe(df_show.set_index("Ville").sort_values("AQI", ascending=False), width='stretch')


    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — Carte horaire
    # ════════════════════════════════════════════════════════════════════════
    with tab_hourly:
        # ── Sélecteur d'heure ───────────────────────────────────────────────
        if data_heure.empty:
            st.info(f"Pas de données pour la date données horaire {sel_date}")
        else : 
            heures_dispo = sorted(data_heure["hour"].dropna().unique().astype(int).tolist())
            heure_labels = {h: data_heure.loc[data_heure["hour"] == h, "hour_formatted"].iloc[0]
                            for h in heures_dispo
                            if not data_heure.loc[data_heure["hour"] == h, "hour_formatted"].empty}

            selected_hour = st.segmented_control(
                "🕐 Heure locale",
                options=heure_labels,
                format_func=lambda h: heure_labels.get(h),
                default=heures_dispo[0] if heures_dispo else None,
                key="hour_ctrl"
            )

            if selected_hour is None:
                st.info("Sélectionnez une heure pour afficher la carte.")
                st.stop()

            df_h = data_heure[data_heure["hour"] == selected_hour].copy()
            col_map_h, col_ctrl_h = st.columns([3, 1])

            with col_ctrl_h:
                map_style_h = st.selectbox("Style carte", ["carto-positron", "open-street-map"], key="style_hourly")
                # size_by_h   = st.selectbox("Taille des points", ["AQI", "PM2.5", "Vent"], key="size_hourly")
                color_by_h  = st.selectbox("Couleur", ["AQI (norme)", "Température"], key="color_hourly")

            # ── Hover horaire ───────────────────────────────────────────────────
            df_h["hover"] = df_h.apply(hover_hourly, axis=1)

            # ── Taille & couleur ────────────────────────────────────────────────
            # size_key_h = {"AQI": "aqi", "PM2.5": "pm25", "Vent": "wind_speed"}[size_by_h]
            # col_min, col_max = df_h[size_key_h].min(), df_h[size_key_h].max()
            # df_h["marker_size"] = (df_h[size_key_h] - col_min) / (col_max - col_min + 1) * 30 + 20

            color_key_h = {"AQI (norme)": "aqi", "Température": "temperature"}[color_by_h]

            # ── Construction de la carte ────────────────────────────────────────
            fig_h = go.Figure()
            for _, row in df_h.iterrows():
                city_name = row["city"]
                if city_name not in CITIES_COORDS:
                    continue
                mc = get_aqi_color(row["aqi"]) if color_by_h == "AQI (norme)" else get_temp_color(row["temperature"])
                fig_h.add_trace(go.Scattermapbox(
                    lat=[CITIES_COORDS[city_name]["lat"]],
                    lon=[CITIES_COORDS[city_name]["lon"]],
                    mode="markers+text",
                    marker=dict(size=25, color=mc, opacity=0.85),
                    text=[city_name], textposition="top center",
                    textfont=dict(size=11, color="#1a1a2e", family="Inter"),
                    hovertext=row["hover"], hoverinfo="text",
                    showlegend=False,
                ))
   
                fig_h.add_trace(go.Scattermapbox(
                    lat=[CITIES_COORDS[city_name]["lat"]],
                    lon=[CITIES_COORDS[city_name]["lon"]],
                    mode="text",
                    text=[f"{row['aqi']:.0f}" if pd.notna(row.get("aqi")) else ""],
                    textfont=dict(size=10, color="white", family="Inter"),
                    hoverinfo="skip", showlegend=False,
                ))

            fig_h.update_layout(
                mapbox=dict(style=map_style_h, center=dict(lat=46.6, lon=2.5), zoom=4.6),
                margin=dict(l=0, r=0, t=0, b=0), height=520,
            )
            with col_map_h:
                st.plotly_chart(fig_h, width='stretch')

            with col_ctrl_h:
                if color_by_h == "AQI (norme)":
                    st.markdown("##### Échelle AQI")
                    for rng, lbl, col in [
                        ("0–50",    "Bon",               "#00c853"),
                        ("51–100",  "Modéré",            "#f9a825"),
                        ("101–150", "Mauvais (sensibles)","#ef6c00"),
                        ("151–200", "Mauvais",            "#c62828"),
                        ("201-300", "Très mauvais",       "#6a1b9a"),
                        (">300",    "Dangereux",          "#6f0909"),
                        ("No data","","#BEBABA")
                    ]:
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
                            f'<div style="width:16px;height:16px;border-radius:50%;background:{col}"></div>'
                            f'<span style="font-size:0.78rem"><b>{rng}</b> {lbl}</span></div>',
                            unsafe_allow_html=True
                        )
                else :   
                    st.markdown("##### Échelle Témpérature")
                    for rng, lbl, col in [
                        ("< -15",    "Froid Extrême", "#4A148C"),
                        ("-15–-5",  "Grand Froid", "#1565C0"),
                        ("-5-0", "Gel","#42A5F5"),
                        ("0-7", "Frais",   "#81C784"),
                        ("7-14", "Douceur", "#CDDC39"),
                        ("14-20", "Agréable", "#FFEB3B"),
                        ("20-25", "Chaud", "#FBC02D"),
                        ("25-30", "Très Chaud", "#FB8C00"),
                        ("30-35", "Forte Chaleur",  "#E53935"),
                        (">35",    "Chaleur Extrême", "#B71C1C"),
                        ("No data","","#BEBABA")
                    ]:
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
                            f'<div style="width:16px;height:16px;border-radius:50%;background:{col}"></div>'
                            f'<span style="font-size:0.78rem"><b>{rng}</b> {lbl}</span></div>',
                            unsafe_allow_html=True
                        )    

            
            # ── Tableau horaire ────────────────────────────────────────────────
            st.markdown("---")
            st.markdown(f"### Tableau horaire — {heure_labels.get(selected_hour, selected_hour)}h")
            cols_show = ["city","aqi","alert_level","pm25","pm10","primary_pollutant",
                        "temperature","feels_like","humidity","pressure_hpa","wind_speed","uvi","weather"]
            cols_labels = ["Ville","AQI","Alerte pollution","PM2.5","PM10","Polluant majoritaire",
                        "Temp °C","Ressenti °C","Humidité %","Pression","Vent m/s","UVI","Météo"]
            df_h_show = df_h[[c for c in cols_show if c in df_h.columns]].copy()
            df_h_show.columns = cols_labels[:len(df_h_show.columns)]
            df_h_show["Alerte pollution"] = df_h_show["AQI"].apply(get_aqi_label) 
            df_h_show["Météo"] = df_h_show["Météo"].map(dicoEN_FR)
            # df_h_show["Alerte météo"] = df_h_show["Alerte météo"].map(dicoEN_FR)
            df_h_show["Alerte météo"] = df_h.apply(
                lambda row : weather_condition_details(
                    feels_like = row["feels_like"],
                    humidity= row["humidity"],
                    wind_speed= row["wind_speed"],
                    wind_gust= row["wind_gust_mps"],
                    uvi = row["uvi"],
                )["details"], axis = 1)
            st.dataframe(df_h_show.set_index("Ville").sort_values("AQI", ascending=False), width='stretch')
        
            
            # ── Graphique horaire ──────────────────────────────────────────────
            # ajouter graph de l'évolution des variables sur la journée ==> données passée et forecast pour le jour J
            
            st.markdown("---")
            st.markdown("### Évolution horaire par ville")
            city_hour = st.selectbox("Ville à afficher",sorted(CITIES_COORDS.keys()),key="x_var_city")
            
        
            # Préparer les données complètes (toutes les heures, pas juste l'heure sélectionnée)
            # if city_hour == "Tout" : 
            #     df_plot = data_heure.dropna(subset=["hour"]).copy()
            # else : 
            df_plot = data_heure.loc[data_heure["city"] == city_hour].copy()
            
            forecast_list = df_plot['last_forecast'].iloc[0]
            meteo_forecast = pd.json_normalize(forecast_list)
            meteo_forecast["date"] = (
                    pd.to_datetime(meteo_forecast["timestamp_utc"])
                    .dt.tz_convert("Europe/Paris")
                    .dt.strftime("%Y-%m-%d")
                )
            meteo_forecast["city"] = city_hour
            # df_plot["hour"] = df_plot["hour"].astype(int)
            meteo_forecast.rename(columns= {"temperature_celsius": "temperature",
                                            "feels_like_celsius" : "feels_like",
                                            "humidity_percent" : "humidity",
                                            "wind_speed_mps" : "wind_speed",
                                            "weather_main" : "weather"},inplace = True)
            
            meteo_forecast["datetime"] = pd.to_datetime(meteo_forecast["date"]) + pd.to_timedelta(meteo_forecast["hour"],unit = "h")
            df_plot["datetime"] = pd.to_datetime(df_plot["date"]) + pd.to_timedelta(df_plot["hour"],unit = "h")
            df_plot = df_plot.sort_values("datetime")
        
            # df_plot.drop(["hour_utc","hour_utc_formatted"],axis = 1,inplace = True)
            # meteo_forecast.drop(["hour_utc","hour_utc_formatted"],axis = 1,inplace = True)
            df_plot = df_plot.drop(["last_forecast"],axis = 1)
            meteo_forecast.drop(["timestamp_utc"],axis = 1,inplace = True)
            actual_hour = df_plot["datetime"].dt.strftime("%d/%m %Hh").iloc[-1]
            df_plot = pd.concat([df_plot, meteo_forecast], axis = 0,ignore_index = True)
                        
            fig_AQI = go.Figure()
            fig_weather = make_subplots(specs=[[{"secondary_y": True}]])
    
            # for city in cities_in_plot:
            df_plot = df_plot[df_plot["city"] == city_hour].sort_values(by = ["datetime"])
            df_plot["x_label"] = df_plot["datetime"].dt.strftime("%d/%m %Hh") 
            
            
            # city_label = TOWNS_BY_NAME[city].name_fr if city in TOWNS_BY_NAME else str.capitalize(city)

            # ── AQI ───────────────────────────────────────────────────────
            aqi_hover = df_plot.apply(
                lambda r: (
                    f"<b>{str.capitalize(g(r, 'city', '?'))}</b> — {g(r, 'hour_formatted', '?')}<br>"
                    f"─────────────────<br>"
                    f"🏭 AQI : <b>{fmt(g(r,'aqi'), '.0f')}</b> ({get_aqi_label(g(r,'aqi'))})<br>"
                    f"🟡 PM10 : <b>{fmt(g(r,'pm10'), '.1f')}</b><br>"
                    f"🔵 PM2.5 : <b>{fmt(g(r,'pm25'), '.1f')}</b><br>"
                    f"🔴 NO₂ : <b>{fmt(g(r,'no2'), '.1f')}</b><br>"
                    f"🟢 O₃ : <b>{fmt(g(r,'o3'), '.1f')}</b>"
                ), axis=1
            ).tolist()

            
            fig_AQI.add_trace(go.Bar(
                x=df_plot["datetime"].dt.strftime("%d/%m %Hh"), 
                y=df_plot["aqi"].tolist(),
                name="AQI moyen",
                hovertext=aqi_hover, 
                hoverinfo="text",
                marker_color=df_plot["aqi"].apply(get_aqi_color).tolist() if city_hour != "Tout" else None,
            ))

            # ── Température & Humidité ─────────────────────────────────────
            temp_hover = df_plot.apply(
                lambda r: (
                    f"<b>{str.capitalize(g(r, 'city', '?'))}</b> — {g(r, 'hour_formatted', '?')}<br>"
                    f"─────────────────<br>"
                    f"🌡️ Temp : <b>{fmt(g(r,'temperature'), '.1f')}°C ( Ressentie : <b>{fmt(g(r,'feels_like'), '.1f')}°) </b><br>"
                    f"💧 Humidité : <b>{fmt(g(r,'humidity'), '.0f')}%</b><br>"
                    f"☀️ UVI : <b>{fmt(g(r,'uvi'), '.1f')} ({dicoEN_FR.get(g(r,'uvi_category','?'))})</b><br>"
                    f"💨 Vent : <b>{fmt(g(r,'wind_speed'), '.1f')} m/s</b><br>"
                    f"⏲ Pression : <b>{fmt(g(r,'pressure_hpa'), '.1f')}</b>"
                ), axis=1
            ).tolist()


            # if city_hour != "Tout":
            fig_weather.add_trace(go.Bar(
                x=df_plot["datetime"].dt.strftime("%d/%m %Hh"), 
                y=df_plot["temperature"].tolist(),
                name="Temp °C",
                marker_color=df_plot["feels_like"].apply(get_temp_color).tolist(), 
                hovertext=temp_hover, hoverinfo="text",
                # opacity=0.5,
            ), secondary_y=False)
            
            fig_weather.add_trace(go.Scatter(
                x=df_plot["datetime"].dt.strftime("%d/%m %Hh"), 
                y=df_plot["humidity"].tolist(),
                mode="lines+markers", 
                name="Humidité %",
                line=dict(width=2), marker=dict(size=7), hoverinfo="skip"
            ), secondary_y=True)
            
            # ── Layouts ────────────────────────────────────────────────────────
            fig_AQI.update_layout(
                title="AQI / heure", height=380,
                xaxis_title="Heure locale", yaxis_title="AQI",
                barmode="group",
                # legend_title="Ville",
                margin=dict(l=10, r=10, t=40, b=20),
                xaxis=dict(
                    tickmode = "array",
                    tickvals = df_plot["datetime"].dt.strftime("%d/%m %Hh"), 
                    ticktext = df_plot["datetime"].dt.strftime("%Hh"),
                    showgrid = True
                ),
                yaxis=dict(showgrid=True))

            fig_weather.update_layout(
                xaxis = dict(
                    tickmode = "array",
                    tickvals = df_plot["datetime"].dt.strftime("%d/%m %Hh"), 
                    ticktext = df_plot["datetime"].dt.strftime("%Hh"),
                    showgrid = False
                ),
                xaxis_title="Heure locale",
                title="Température & Humidité / heure", height=380,
                barmode="group",
                # legend_title="Ville",
                margin=dict(l=10, r=10, t=40, b=20))
            
            jours_fr = {
                "Monday": "Lun",
                "Tuesday": "Mar",
                "Wednesday": "Mer",
                "Thursday": "Jeu",
                "Friday": "Ven",
                "Saturday": "Sam",
                "Sunday": "Dim",
            }
            for fig in [fig_weather, fig_AQI]:

                for i, day in enumerate(df_plot["datetime"].dt.date.unique()):

                    df_day = df_plot[df_plot["datetime"].dt.date == day]

                    x0 = df_day["datetime"].dt.strftime("%d/%m %Hh").iloc[0]
                    x1 = df_day["datetime"].dt.strftime("%d/%m %Hh").iloc[-1]
                    day_name_en = pd.to_datetime(day).strftime("%A")
                    day_name_fr = jours_fr[day_name_en]
                    
                    fig.add_vrect(
                        x0=x0,
                        x1=x1,
                        fillcolor="lightgrey" if i % 2 == 0 else "lightblue",
                        opacity=0.12,
                        layer="below",
                        line_width=0,
                        annotation_text=f"{day_name_fr} {pd.to_datetime(day).strftime('%d/%m')}",
                        annotation_position="top left"
                    )
                    fig.add_shape(type="line", x0=actual_hour,x1=actual_hour)
                    
                    # fig.add_vline(
                    #     x=df_plot["datetime"].dt.strftime("%d/%m %Hh")[0],
                    #     line_dash="dash",
                    #     line_width=0.5,

                    #     annotation_text="Prévisions",
                    #     annotation_position="top"
                    # )
            
            # fig_AQI.add_vline(x=first_x, line_dash="dash", line_color="gray")
            
            fig_weather.update_yaxes(title_text="°C", secondary_y=False, showgrid=False)
            fig_weather.update_yaxes(title_text="% Hum", secondary_y=True, showgrid=False)

            # with col_AQI:
            st.plotly_chart(fig_AQI, width="stretch")
            # with col_temp:
            st.plotly_chart(fig_weather, width="stretch")
            
            # conseil
            st.markdown("---")
            st.markdown("#### Recommendations pour la dernière heure")
            actual_hour = df_plot["hour_formatted"].iloc[-1]
            st.markdown(advisory_html(df_plot[df_plot["hour_formatted"]==actual_hour]['aqi'].mean()), unsafe_allow_html=True)
            st.markdown("---")
           
            
# ============================================================
# PAGE 2 – KPI & POLLUTION
# ============================================================
elif page == "📊  KPI & Pollution":
    st.markdown('<div class="main-header">📊 KPI Qualité de l\'Air & Météo</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">Données du <b>{date_range}</b>  Survolez une ville pour tous les détails</div>', unsafe_allow_html=True)

    # faire check box pour décider si date unique ou période
    
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2],vertical_alignment="bottom")
    
    with col_f1:
        # compare_mode = st.checkbox("Comparer avec une autre ville")
        selected_city = st.selectbox("Ville à afficher",
                                     options=["Toute les villes"] + sorted(CITIES_COORDS.keys()))
    with col_f2:
        # if compare_mode:
            # city2 = st.selectbox("🏢Ville 2", [c for c in sorted(df_main["city"].unique()) if c != selected_city])
        # else:
            # city2 = None
        filter_mode = st.selectbox(
        "Filtrer par",
        options=["Période", "Mois", "Saison", "Année"],
        key="kpi_filter_mode"
    )
    
    with col_f3:
        seasons = {
        "Printemps": [3, 4, 5],
        "Été":       [6, 7, 8],
        "Automne":   [9, 10, 11],
        "Hiver":     [12, 1, 2]
        }
        
        #Date
        if filter_mode == "Période":
            date_range = st.date_input(
            "Période",
            value=[datetime(2026, 1, 1), datetime(2026, 12, 31)],
            format="DD/MM/YYYY",
            key="kpi_period"
            )
            if len(date_range) == 2:
                d_start, d_end = str(date_range[0]), str(date_range[1])
            else:
                d_start, d_end = date_range[0], date_range[0]   
        
        #Mois
        elif filter_mode == "Mois":
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                selected_year_m = st.selectbox("Année", options=[2025, 2026], index=1, key="kpi_year_m")
            with col_m2:
                selected_month = st.selectbox(
                    "Mois",
                    options=list(range(1, 13)),
                    format_func=lambda m: datetime(2026, m, 1).strftime("%B").capitalize(),
                    index=datetime.today().month - 1,
                    key="kpi_month"
                )
            d_start = f"{selected_year_m}-{selected_month:02d}-01"
            last_day = (datetime(selected_year_m, selected_month % 12 + 1, 1) - pd.Timedelta(days=1)).day \
                    if selected_month < 12 else 31
            d_end = f"{selected_year_m}-{selected_month:02d}-{last_day:02d}"
        
        #Saison
        elif filter_mode == "Saison":
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                selected_year_s = st.selectbox("Année", options=[2025, 2026], index=1, key="kpi_year_s")
            with col_s2:
                selected_saison = st.selectbox("Saison", options=list(seasons.keys()), key="kpi_saison")
            mois_saison = seasons[selected_saison]
            # Hiver : décembre de l'année précédente + jan/fev de l'année courante
            if selected_saison == "❄️ Hiver":
                d_start = f"{selected_year_s - 1}-12-01"
                d_end   = f"{selected_year_s}-02-28"
            else:
                d_start = f"{selected_year_s}-{mois_saison[0]:02d}-01"
                d_end   = f"{selected_year_s}-{mois_saison[-1]:02d}-30"
    
        # Année
        else: 
            selected_year = st.selectbox("Année", options=[2025, 2026], index=1, key="kpi_year")
            d_start = f"{selected_year}-01-01"
            d_end   = f"{selected_year}-12-31"
    
    

    # df avec une seule date
    # df_agg  = load_agg_data(date=today_date.isoformat())
    df_agg  = load_agg_data(date_start=d_start,date_end=d_end)
    # df_city = df_main[(df_main["city"] == selected_city) & (df_main["date"] >= d_start) & (df_main["date"] <= d_end)].sort_values("date")
    if selected_city == "Toute les villes" :
        df_city = df_agg[(df_agg["date"] >= d_start) & (df_agg["date"] <= d_end)].sort_values("date")
    else : 
        df_city = df_agg[(df_agg["city"] == selected_city) & (df_agg["date"] >= d_start) & (df_agg["date"] <= d_end)].sort_values("date")


    # df avec range de date
    # df_period  = load_agg_data(date_start=d_start, date_end=d_end)
    
    # latest  = df_city.iloc[-1] if not df_city.empty else None
    # latest  = df_period.iloc[-1] if not df_period.empty else None
    # st.dataframe(df_city)
    st.write(df_city['pol_aqi_trend'].mode()[0])
    if df_city.empty :
        st.warning("Aucune donnée pour cette sélection.")
        st.stop()

    # ── KPI Row ──
    st.markdown("###  Indicateurs Clés")
    k = st.columns(5)
    def kpi(col, val, label, bg_color="#4361ee"):
        col.markdown(
        f'<div class="kpi-box" style="background: linear-gradient(135deg, {bg_color}cc, {bg_color});">'
        f'<div class="kpi-val">{val}</div>'
        f'<div class="kpi-lbl">{label}</div>'
        f'</div>',
        unsafe_allow_html=True
    )
    
    kpi(k[0], f"{df_city['pol_avg_aqi'].mean():.0f}",       "🏭 AQI Moyen", get_aqi_color(df_city['pol_avg_aqi'].mean()))
    kpi(k[1], f"{df_city['pol_avg_pm25'].mean():.0f}",      "🔵 PM2.5",get_aqi_color(df_city['pol_avg_pm25'].mean()))
    kpi(k[2], f"{df_city['pol_avg_pm10'].mean():.0f}",      "🟡 PM10",get_aqi_color(df_city['pol_avg_pm10'].mean()))
    kpi(k[3], f"{df_city['pol_avg_no2'].mean():.0f}",       "🔴 NO₂",get_aqi_color(df_city['pol_avg_no2'].mean()))
    kpi(k[4], f"{df_city['pol_avg_o3'].mean():.0f}","🟢 O3", get_aqi_color(df_city['pol_avg_o3'].mean()))

    k2 = st.columns(5)
    kpi(k2[0], f"{df_city['w_avg_temperature'].mean():.1f}°C",   "🌡️ Température")
    kpi(k2[1], f"{df_city['w_avg_humidity'].mean():.0f}%",       "💧 Humidité")
    kpi(k2[2], f"{df_city['w_avg_wind_speed'].mean():.1f} m/s",  "💨 Vent")
    kpi(k2[3], f"{df_city['w_avg_uvi'].mean():.2f}",      " UV")
    # kpi(k2[4], trend_icon(df_city['pol_aqi_trend'].mode()),         "📈 Tendance AQI")

    # conseil
    st.markdown(advisory_html(df_city['pol_avg_aqi'].mode()[0]), unsafe_allow_html=True)
    st.markdown("---")

    # ── Charts ──
    st.markdown(f"####  Evolution journalière polluants — {selected_city}")
    st.markdown(f"")
    col_l, col_r = st.columns(2)
    
    
    #aqi/jour
    with col_l:
        # st.markdown("#### Évolution de l'AQI dans le temps")
        fig_aqi = go.Figure()
        fig_aqi.add_hrect(y0=0,   y1=50,  fillcolor="#00c853", opacity=0.1)
        fig_aqi.add_hrect(y0=50,  y1=100, fillcolor="#f9a825", opacity=0.1)
        fig_aqi.add_hrect(y0=100, y1=150, fillcolor="#ef6c00", opacity=0.1)
        fig_aqi.add_hrect(y0=150, y1=200, fillcolor="#e63131", opacity=0.1)
        fig_aqi.add_hrect(y0=200, y1=300, fillcolor="#6a1b9a", opacity=0.1)
        # fig_aqi.add_hrect(y0=300, y1=500, fillcolor="#6f0909", opacity=0.06)

        fig_aqi.add_trace(go.Scatter(x=df_city["date"], y=df_city["pol_max_aqi"], name="Max"
                                     , line=dict(color="#ef6c00", dash="dot", width=1.5)))
        fig_aqi.add_trace(go.Scatter(x=df_city["date"], y=df_city["pol_min_aqi"], name="Min",
                                     line=dict(color="#00c853", dash="dot", width=1.5)))
        fig_aqi.add_trace(go.Bar(x=df_city["date"], y=df_city["pol_avg_aqi"], name="Moyenne",
                                 marker_color=df_city["pol_avg_aqi"].apply(get_aqi_color).to_list()))
            
            # line=dict(color="#4361ee", width=2.5), fill="tozeroy", fillcolor="rgba(67,97,238,0.1)", mode="lines+markers"))
        # if city2:
        #     df_c2 = df_main[(df_main["city"] == city2) & (df_main["date"] >= d_start) & (df_main["date"] <= d_end)].sort_values("date")
        #     fig_aqi.add_trace(go.Scatter(x=df_c2["date"], y=df_c2["avg_aqi"], name=city2,
        #         line=dict(color="#f77f00", width=2, dash="dash"), mode="lines+markers"))
        fig_aqi.update_layout( title="Evolution AQI/jour",height=340, legend=dict(orientation="v", y=0.9), margin=dict(l=10,r=10,t=20,b=20), yaxis_title="AQI")
        st.plotly_chart(fig_aqi, width='stretch')


    # polluant/jour
    # ── Granularité selon filter_mode ─────────────────────────────────
    with col_r:

        # Définir les options de granularité selon le filtre actif
        granularity_options = {
            "Période": ["Jour", "Mois", "Année"],
            "Mois":    ["Jour"],
            "Saison":  ["Saison"],
            "Année":   ["Mois", "Année"],
        }
        options_dispo = granularity_options[filter_mode]

        if len(options_dispo) > 1:
            granularity = st.segmented_control(
                "Granularité",
                options=options_dispo,
                default=options_dispo[0],
                key="granularity_pol"
            )
        else:
            granularity = options_dispo[0]
            
        # ── Agrégation selon la granularité ───────────────────────────
        df_pol = df_city.copy()
        df_pol["date"] = pd.to_datetime(df_pol["date"])

        POL_COLS = ["pol_avg_pm25", "pol_avg_pm10", "pol_avg_no2", "pol_avg_o3"]

        if granularity == "Jour":
            df_pol["x_label"] = df_pol["date"].dt.strftime("%d/%m/%Y")
            df_grouped = df_pol.groupby("x_label", sort=False)[POL_COLS].mean().reset_index()
            # Conserver l'ordre chronologique
            df_grouped = df_pol[["x_label"]].drop_duplicates().merge(df_grouped, on="x_label")

        elif granularity == "Mois":
            df_pol["x_label"] = df_pol["date"].dt.strftime("%b %Y")
            df_pol["x_sort"]  = df_pol["date"].dt.to_period("M")
            df_grouped = df_pol.groupby(["x_sort", "x_label"])[POL_COLS].mean().reset_index()
            df_grouped = df_grouped.sort_values("x_sort")

        elif granularity == "Année":
            df_pol["x_label"] = df_pol["date"].dt.strftime("%Y")
            df_grouped = df_pol.groupby("x_label")[POL_COLS].mean().reset_index()
            df_grouped = df_grouped.sort_values("x_label")

        elif granularity == "Saison":
            def get_season(month):
                if month in [3, 4, 5]:  return "Printemps"
                if month in [6, 7, 8]:  return "Été"
                if month in [9, 10, 11]: return "Automne"
                return "Hiver"
            df_pol["x_label"] = df_pol["date"].dt.month.apply(get_season)
            season_order = ["Hiver", "Printemps", "Été", "Automne"]
            df_pol["x_sort"] = df_pol["x_label"].map({s: i for i, s in enumerate(season_order)})
            df_grouped = df_pol.groupby(["x_sort", "x_label"])[POL_COLS].mean().reset_index()
            df_grouped = df_grouped.sort_values("x_sort")

        x_vals = df_grouped["x_label"].tolist()
        
        # ── Figure ────────────────────────────────────────────────────
        fig_p = go.Figure()
        fig_p.add_trace(go.Bar(x=x_vals, y=df_grouped["pol_avg_pm25"], name="PM2.5",
                            marker_color="#4361ee", opacity=0.8))
        fig_p.add_trace(go.Bar(x=x_vals, y=df_grouped["pol_avg_pm10"], name="PM10",
                            marker_color="#3a86ff", opacity=0.6))
        fig_p.add_trace(go.Bar(x=x_vals, y=df_grouped["pol_avg_no2"],  name="NO₂",
                            marker_color="#3cf71f", opacity=0.6))
        fig_p.add_trace(go.Bar(x=x_vals, y=df_grouped["pol_avg_o3"],   name="O₃",
                            marker_color="#f9ae18", opacity=0.6))

        fig_p.update_layout(
            title=f"Évolution polluants / {granularity.lower()}",
            height=340,
            barmode="group",
            legend=dict(orientation="v", y=1),
            margin=dict(l=10, r=10, t=40, b=20),
            yaxis_title="AQi",
            xaxis_title=granularity,
        )
        st.plotly_chart(fig_p,width='stretch')
        
        # st.markdown("####  Polluants principaux")
        fig_p = make_subplots(specs=[[{"secondary_y": True}]])
        fig_p.add_trace(go.Bar(x=df_city["date"], y=df_city["pol_avg_pm25"], name="PM2.5",
                               marker_color="#4361ee", opacity=0.8), secondary_y=False)
        fig_p.add_trace(go.Bar(x=df_city["date"], y=df_city["pol_avg_pm10"], name="PM10",   
                               marker_color="#3a86ff", opacity=0.6), secondary_y=False)
        fig_p.add_trace(go.Bar(x=df_city["date"], y=df_city["pol_avg_no2"], name="NO₂",
                                   marker_color="#3cf71f", opacity=0.6), secondary_y=False)
        fig_p.add_trace(go.Bar(x=df_city["date"], y=df_city["pol_avg_o3"],  name="O₃",
                                   marker_color="#f9ae18", opacity=0.6), secondary_y=False)
        
        fig_p.update_layout(title = "Évolution polluants/jour",height=340, legend=dict(orientation="v", y=1), barmode="group", margin=dict(l=10,r=10,t=20,b=20))
        fig_p.update_yaxes(title_text="PM", secondary_y=False)
        fig_p.update_yaxes(title_text="NO₂ / O₃", secondary_y=True)
        st.plotly_chart(fig_p, width='stretch')


    # ── Hourly data ──
    st.markdown("---")
    st.markdown(f"####  Evolution Horaire — {selected_city} ({d_start})")
    
    
    if selected_city == "Toute les villes" : 
        df_air  = load_hourly_data("gold_air_quality_daily", date = None,date_end=d_end,date_start=d_start)
        df_meteo = load_hourly_data("gold_weather_daily", date = None,date_end=d_end, date_start=d_start)
    else : 
        df_air  = load_hourly_data("gold_air_quality_daily", date = None,date_end=d_end,date_start=d_start,city = selected_city)
        df_meteo = load_hourly_data("gold_weather_daily", date = None,date_end=d_end, date_start=d_start,city = selected_city)
    
    if not df_air.empty and not df_meteo.empty : 
            df_hourly = pd.merge(
            df_air, df_meteo,
            on=["date", "city", "hour_utc", "hour_utc_formatted", "hour", "hour_formatted"],
            how="outer"
            )
        
    elif df_air.empty and not df_meteo.empty : 
            df_hourly = df_meteo
        
    elif not df_air.empty and df_meteo.empty : 
            df_hourly = df_air
    
    
    # df_hourly = load_hourly_period(selected_city,d_start,d_end)
    st.dataframe(df_hourly)
    if df_hourly.empty : 
        st.info("Pas de données horaires pour cette sélection")
    else : 
        
    # Agréger par heure (moyenne sur la période) pour avoir une courbe représentative
        numeric_cols = [c for c in df_hourly.select_dtypes(include="number").columns if c != "hour_utc"]
        df_h = (
            df_hourly.groupby("hour_utc")[numeric_cols]
            .mean()
            .reset_index()
            .sort_values("hour_utc")
        )
        # Reconstruire hour_formatted depuis hour_utc
        df_h["hour_label"] = df_h["hour_utc"].astype(int).apply(lambda h: f"{h:02d}h")

        col_AQI, col_temp = st.columns(2)

        with col_AQI:
            fig_AQI = go.Figure()
            fig_AQI.add_trace(go.Bar(
                x=df_h["hour_label"],
                y=df_h["aqi"].round(0),
                name="AQI moyen",
                marker_color=df_h["aqi"].apply(get_aqi_color).tolist(),
                hovertemplate=(
                    "<b>🕐 %{x}</b><br>"
                    "🏭 AQI : <b>%{y:.0f}</b><br>"
                    "🟡 PM10 : <b>%{customdata[0]:.1f}</b><br>"
                    "🔵 PM2.5 : <b>%{customdata[1]:.1f}</b><extra></extra>"
                ),
                customdata=df_h[["pm10", "pm25"]].values
            ))
            fig_AQI.update_layout(
                height=280, title="AQI moyen / heure",
                xaxis_title="Heure (UTC)", yaxis_title="AQI",
                margin=dict(l=10, r=10, t=40, b=20)
            )
            st.plotly_chart(fig_AQI, width='stretch')

        with col_temp:
            fig_weather = make_subplots(specs=[[{"secondary_y": True}]])
            fig_weather.add_trace(go.Scatter(
                x=df_h["hour_label"], y=df_h["temperature"],
                name="Temp °C",
                line=dict(color="#ef233c", width=2.5),
                mode="lines+markers",
                hovertemplate=(
                    "<b>🕐 %{x}</b><br>"
                    "🌡️ Temp : <b>%{y:.1f}°C</b><br>"
                    "🌡️ Ressentie : <b>%{customdata[0]:.1f}°C</b><br>"
                    "💧 Humidité : <b>%{customdata[1]:.0f}%</b><extra></extra>"
                ),
                customdata=df_h[["temperature", "humidity"]].values
            ), secondary_y=False)
            fig_weather.add_trace(go.Bar(
                x=df_h["hour_label"], y=df_h["humidity"],
                name="Humidité %",
                marker_color="#3a86ff", opacity=0.5,
                hoverinfo="skip"
            ), secondary_y=True)
            fig_weather.update_layout(
                height=280, title="Température & Humidité / heure",
                margin=dict(l=10, r=10, t=40, b=20),
                legend=dict(orientation="h")
            )
            fig_weather.update_yaxes(title_text="°C", secondary_y=False)
            fig_weather.update_yaxes(title_text="% Hum", secondary_y=True)
            st.plotly_chart(fig_weather, width='stretch')

    
    # ── Gauges ──
    # st.markdown("---")
    # st.markdown("####  Jauges")
    # g1, g2, g3, g4 = st.columns(4)

    # def gauge(col, val, title, rng, steps, color):
    #     fig = go.Figure(go.Indicator(
    #         mode="gauge+number",
    #         value=val,
    #         title={"text": title, "font": {"size": 13}},
    #         gauge={"axis": {"range": rng}, "bar": {"color": color}, "steps": steps, "borderwidth": 1}
    #     ))
    #     fig.update_layout(height=200, margin=dict(l=10,r=10,t=30,b=10))
    #     col.plotly_chart(fig, width='stretch')

    # gauge(g1, latest["pol_avg_aqi"],         "AQI",          [0,320],  [{"range":[0,50],"color":"#b2fbd0"},{"range":[50,100],"color":"#fef9c3"},{"range":[100,150],"color":"#f4a05b"},{"range":[150,200],"color":"#ea5b5b"},{"range":[200,320],"color":"#8e53b2"},{"range":[300,400],"color":"#1d1b1e"}], get_aqi_color(latest["pol_avg_aqi"]))
    # gauge(g2, latest["w_avg_temperature"],  "Température °C",[-5,40], [{"range":[-5,8],"color":"#dbeafe"},{"range":[8,25],"color":"#d1fae5"},{"range":[25,40],"color":"#fee2e2"}],       "#ef233c")
    # gauge(g3, latest["w_avg_humidity"],     "Humidité %",   [0,100],  [{"range":[0,40],"color":"#fef9c3"},{"range":[40,70],"color":"#d1fae5"},{"range":[70,100],"color":"#dbeafe"}],    "#3a86ff")
    # gauge(g4, latest["w_avg_wind_speed"],   "Vent m/s",     [0,15],   [{"range":[0,3],"color":"#d1fae5"},{"range":[3,8],"color":"#fef9c3"},{"range":[8,15],"color":"#fee2e2"}],         "#fb8500")


    
    # # ── Radar Chart ──
    # st.markdown("---")
    # st.markdown("####  Profil Global de la Ville")
    # cats = ["AQI norm.", "PM2.5 norm.", "Temp norm.", "Humidité", "Qualité ext.", "Risque santé"]
    # vals_city = [
    #     min(100, latest["pol_avg_aqi"] / 1.5),
    #     min(100, latest["pol_avg_pm25"] / 1.5),
    #     min(100, (latest["w_avg_temperature"] + 5) * 2),
    #     latest["w_avg_humidity"],
    #     latest.get("outdoor_activity_score", 70),
    #     latest["pol_avg_health_risk_score"] * 5,
    # ]
    # fig_radar = go.Figure(go.Scatterpolar(r=vals_city+[vals_city[0]], theta=cats+[cats[0]], fill="toself", name=selected_city, line_color="#4361ee", fillcolor="rgba(67,97,238,0.2)"))
    # # if city2:
    # #     l2 = df_main[(df_main["city"]==city2)&(df_main["date"]==d_end)].iloc[0] if not df_main[(df_main["city"]==city2)&(df_main["date"]==d_end)].empty else None
    # #     if l2 is not None:
    # #         v2 = [min(100,l2["avg_aqi"]/1.5), min(100,l2["avg_pm25"]/1.5), min(100,(l2["avg_temperature"]+5)*2), l2["avg_humidity"], l2.get("outdoor_activity_score",70), l2["avg_health_risk_score"]*5]
    # #         fig_radar.add_trace(go.Scatterpolar(r=v2+[v2[0]], theta=cats+[cats[0]], fill="toself", name=city2, line_color="#f77f00", fillcolor="rgba(247,127,0,0.2)"))
    # fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 110])), height=350, showlegend=True, margin=dict(l=30,r=30,t=30,b=30))
    # col_rad, _ = st.columns([1,1])
    # with col_rad:
    #     st.plotly_chart(fig_radar, use_container_width=True)


# ============================================================
# PAGE 3 – ALERTES & PRÉVISIONS
# ============================================================
## Sur les prévisions récupérer la ou severité est severe,extreme,moderate?
## la ou entre deux jours le delta de température, vent,humidité dépasse un seuil ()
## les prévision météo extreme : heavy..., extreme... orage


elif page == "🚨  Alertes & Prévisions":
    st.markdown('<div class="main-header">🚨 Alertes & Prévisions</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Détection des variations extrêmes — Prévisons sur 7 jours</div>', unsafe_allow_html=True)
    # st.markdown('<div class="sub-header">Détection automatique des variations extrêmes — Forecast 7 jours</div>', unsafe_allow_html=True)


    ALERT_THRESH = {"AQI": 20, "PM2.5": 18, "PM10": 15, "NO₂": 10,
                    "Température": 5, "Humidité": 20,"Vent": 12,}

    forecast_dates_raw = pd.date_range("2026-03-06", periods=7, freq="D")
    forecast_date_strs = [d.strftime("%Y-%m-%d") for d in forecast_dates_raw]

    @st.cache_data
    def build_forecasts(df_main):
        city_fc = {}
        for city in CITIES_COORDS:

            city_df = (
                df_main[df_main["city"] == city]
                .sort_values("date")
            )

            if city_df.empty:
                continue

            last = city_df.iloc[-1]

            rng = np.random.RandomState(abs(hash(city)) % 9999)

            aqi_fc  = [float(last.get("aqi", 50))]
            pm25_fc = [float(last.get("pm25", 20))]
            pm10_fc = [float(last.get("pm10", 30))]
            no2_fc  = [float(last.get("no2", 15))]

            temp_fc = [float(last.get("temperature_celsius", 18))]
            hum_fc  = [float(last.get("humidity_percent", 60))]
            wind_fc = [float(last.get("wind_speed_mps", 15))]

            for _ in range(7):

                aqi_fc.append(
                    max(10, min(200, aqi_fc[-1] + rng.normal(0, 10)))
                )

                pm25_fc.append(
                    max(5, min(180, pm25_fc[-1] + rng.normal(0, 8)))
                )

                pm10_fc.append(
                    max(5, min(160, pm10_fc[-1] + rng.normal(0, 7)))
                )

                no2_fc.append(
                    max(2, min(120, no2_fc[-1] + rng.normal(0, 5)))
                )

                temp_fc.append(
                    max(-10, min(45, temp_fc[-1] + rng.normal(0, 3)))
                )

                hum_fc.append(
                    max(10, min(100, hum_fc[-1] + rng.normal(0, 12)))
                )

                wind_fc.append(
                    max(0, min(130, wind_fc[-1] + rng.normal(0, 10)))
                )

            city_fc[city] = {

                "dates": ["2026-03-05"] + forecast_date_strs,

                # Pollution
                "aqi": [round(v, 1) for v in aqi_fc],
                "pm25": [round(v, 1) for v in pm25_fc],
                "pm10": [round(v, 1) for v in pm10_fc],
                "no2": [round(v, 1) for v in no2_fc],

                # Météo
                "temperature": [round(v, 1) for v in temp_fc],
                "humidity": [round(v, 1) for v in hum_fc],
                "wind": [round(v, 1) for v in wind_fc],
            }

        return city_fc

    date_forecast = st.date_input("Sélectionnez une date (aujourd'hui par défaut)", value = 'today'
                             ,format = "DD-MM-YYYY",key = "map_date")
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
    st.dataframe(city_forecasts.head())
    # forecast = build_forecasts(city_forecasts)
    alert_level = ["moderate","severe","extreme"]
    
    # Detect alerts
    metric_keys = {"AQI": "aqi","PM2.5": "pm25","PM10": "pm10","NO₂": "no2",
    "Température": "temperature","Humidité": "humidity","Vent": "wind",
    }   
    
    all_alerts = []
    for city, fc in city_forecasts.items():
        for metric, thresh in ALERT_THRESH.items():
            key=metric_keys[metric]
            if key not in fc:
                continue
            # series = fc[metric.lower().replace(".", "").replace("₂","2").replace("₃","3")]
            series = fc[key]
            for i in range(1, len(series)):
                delta = series[i] - series[i-1]
                if abs(delta) >= thresh:
                    severity = "🔴 Critique" if abs(delta) >= thresh * 1.7 else "🟠 Élevée"
                    all_alerts.append({
                        "severity": severity, "city": city,
                        "date": fc["dates"][i], "metric": metric,
                        "valeur_actuelle": series[i-1], "valeur_prévue": series[i],
                        "variation": round(delta, 1), "direction": "📈 Hausse" if delta > 0 else "📉 Baisse",
                    })

    n_crit = sum(1 for a in all_alerts if "Critique" in a["severity"])
    n_high = sum(1 for a in all_alerts if "Élevée"  in a["severity"])
    cit_alert = set(a["city"] for a in all_alerts)

    # Summary KPIs
    sa, sb, sc, sd = st.columns(4)
    sa.metric("⚠️ Total alertes (7j)", len(all_alerts))
    sb.metric("🔴 Critiques",  n_crit)
    sc.metric("🟠 Élevées",    n_high)
    sd.metric("🏙️ Villes touchées", len(cit_alert))

    # Controls
    st.markdown("---")
    cc1, cc2, cc3 = st.columns([2, 1, 1])
    with cc1:
        sel_cities_fc = st.multiselect("Villes à afficher", list(CITIES_COORDS.keys()), default=["paris", "lille", "bordeaux"])
    with cc2:
        fc_metric = st.selectbox("Indicateur prévision", ["AQI", "PM2.5", "PM10", "NO₂","Température","Humidité","Vent"])
    with cc3:
        sev_filter = st.multiselect("Filtre sévérité", ["🔴 Critique", "🟠 Élevée"], default=["🔴 Critique", "🟠 Élevée"])

    # fc_key = fc_metric.lower().replace(".", "").replace("₂","2").replace("₃","3")
    
    fc_key = metric_keys[fc_metric]
    # Forecast chart
    fig_fc = go.Figure()
    colors_fc = ["#4361ee","#ef233c","#06d6a0","#fb8500","#8338ec","#3a86ff","#ff006e","#ffbe0b"]
    for i, city in enumerate(sel_cities_fc):
        if city not in city_forecasts: continue
        fc = city_forecasts[city]
        clr = colors_fc[i % len(colors_fc)]
        vals = fc.get(fc_key, fc["aqi"])
        # Historical point
        fig_fc.add_trace(go.Scatter(x=[fc["dates"][0]], y=[vals[0]], mode="markers",
            marker=dict(size=12, color=clr, symbol="star"), name=f"{city} (actuel)", showlegend=True))
        # Forecast line
        fig_fc.add_trace(go.Scatter(x=fc["dates"][1:], y=vals[1:], mode="lines+markers",
            line=dict(color=clr, dash="dot", width=2.2), name=f"{city} prévision"))
        # Confidence band (±σ)
        sig = 8
        upper = [v + sig for v in vals[1:]]
        lower = [v - sig for v in vals[1:]]
        fig_fc.add_trace(go.Scatter(
            x=fc["dates"][1:] + fc["dates"][1:][::-1], y=upper + lower[::-1],
            fill="toself", fillcolor=f"rgba({int(clr[1:3],16)},{int(clr[3:5],16)},{int(clr[5:],16)},0.08)",
            line=dict(color="rgba(0,0,0,0)"), showlegend=False, hoverinfo="skip"))

    # Alert threshold
    thresh_line = {"AQI": 100, "PM2.5": 75, "PM10": 50, "NO₂": 40,
                   "Température": 35,"Humidité": 85, "Vent": 70}.get(fc_metric, 100)
    fig_fc.add_hline(y=thresh_line, line_dash="dash", line_color="red", line_width=1.5,
                     annotation_text=f"Seuil alerte OMS ({thresh_line})", annotation_position="bottom right")

    fig_fc.update_layout(height=400, title=f"Prévisions {fc_metric} — 7 prochains jours",
        xaxis_title="Date", yaxis_title=fc_metric,
        legend=dict(orientation="h", y=1.12), margin=dict(l=20,r=20,t=60,b=20))
    st.plotly_chart(fig_fc, width='stretch')

    # Alert table
    st.markdown("---")
    st.markdown("### 📋 Détail des Alertes")
    df_alrt = pd.DataFrame([a for a in all_alerts if a["severity"] in sev_filter])
    if df_alrt.empty:
        st.success("Aucune alerte pour les critères sélectionnés.")
    else:
        st.dataframe(
            df_alrt.rename(columns={"severity":"Sévérité","city":"Ville","date":"Date","metric":"KPI",
                "valeur_actuelle":"Valeur J","valeur_prévue":"Valeur J+1","variation":"Variation","direction":"Sens"})
                   .sort_values(["Sévérité","Date"]),
             hide_index=True
        )

    # # Alert map
    # st.markdown("---")
    # st.markdown("### 🗺️ Carte des Alertes Prévues")
    # severity_map = {}
    # for a in all_alerts:
    #     c = a["city"]
    #     if c not in severity_map or ("Critique" in a["severity"] and "Critique" not in severity_map.get(c,"")):
    #         severity_map[c] = a["severity"]

    # map_rows_alert = []
    # for city, coords in CITIES_COORDS.items():
    #     sev = severity_map.get(city, "✅ OK")
    #     col_a = "#ff0000" if "Critique" in sev else "#f77f00" if "Élevée" in sev else "#00c853"
    #     sz   = 30 if "Critique" in sev else 22 if "Élevée" in sev else 14
    #     map_rows_alert.append({"city": city, "lat": coords["lat"], "lon": coords["lon"], "sev": sev, "col": col_a, "sz": sz})

    # fig_amap = go.Figure()
    # for r in map_rows_alert:
    #     fig_amap.add_trace(go.Scattermapbox(
    #         lat=[r["lat"]], lon=[r["lon"]],
    #         mode="markers+text",
    #         marker=dict(size=r["sz"], color=r["col"], opacity=0.85),
    #         text=[r["city"]], textposition="top center",
    #         hovertext=f"<b>{r['city']}</b><br>{r['sev']}",
    #         hoverinfo="text", showlegend=False,
    #     ))
    # fig_amap.update_layout(
    #     mapbox=dict(style="carto-positron", center=dict(lat=46.6, lon=2.5), zoom=4.6),
    #     height=420, margin=dict(l=0,r=0,t=0,b=0)
    # )
    # st.plotly_chart(fig_amap, use_container_width=True)

    # al_leg_c1, al_leg_c2, al_leg_c3 = st.columns(3)
    # al_leg_c1.markdown('<div style="color:#ff0000;font-weight:700">🔴 Alerte Critique : variation ≥ 34 unités</div>', unsafe_allow_html=True)
    # al_leg_c2.markdown('<div style="color:#f77f00;font-weight:700">🟠 Alerte Élevée  : variation ≥ 20 unités</div>', unsafe_allow_html=True)
    # al_leg_c3.markdown('<div style="color:#00c853;font-weight:700">✅ OK : pas de variation significative</div>', unsafe_allow_html=True)


# ============================================================
# PAGE 4 – CORRÉLATIONS
# ============================================================
elif page == "   Corrélations":
    st.markdown('<div class="main-header">🔗 Analyse des Corrélations</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Identification des variables fortement corrélées avec la qualité de l\'air</div>', unsafe_allow_html=True)

    df_main  = load_agg_data(date_start="2026-04-01")
    df_main["w_precipitation_detected"] = df_main["w_precipitation_detected"].replace({True : 1,
                                                                             False : 0})
    # st.dataframe(df_main.head())
    # st.write(df_main.columns)

    
    NUM_COLS  = ["pol_avg_aqi","pol_aqi_volatility","pol_avg_pm25","pol_avg_pm10","pol_avg_no2","pol_avg_o3","pol_avg_co","pol_avg_so2","pol_avg_health_risk_score"
                 ,"w_avg_temperature","w_avg_feels_like","w_avg_humidity","w_avg_pressure","w_avg_wind_speed","w_avg_uvi","w_precipitation_detected"]
    NICE_LABS = ["AQI","Volatilité AQI","PM2.5","PM10","NO₂","O₃","CO","SO₂","Risque santé",
                 "Température","Température_ressentie","Humidité","Pression","Vent","UV","Précipitation"]
    
    lab_map   = dict(zip(NUM_COLS, NICE_LABS))

    # filter_city_corr = st.multiselect("Filtrer par ville (laisser vide = toutes)", sorted(df_main["city"].unique()))
    # df_c = df_main[df_main["city"].isin(filter_city_corr)] if filter_city_corr else df_main
    df_c = df_main
    df_corr_data = df_c[NUM_COLS].dropna()
    corr = df_corr_data.corr()

    col_heat, col_rank = st.columns([3, 2])

    # with col_heat:
    st.markdown("####  Matrice de Corrélation")
    ztext = [[f"{v:.2f}" for v in row] for row in corr.values]
    fig_heat = go.Figure(go.Heatmap(
        z=corr.values, x=NICE_LABS, y=NICE_LABS,
        colorscale="RdBu_r", zmid=0,
        text=ztext, texttemplate="%{text}", textfont={"size": 10},
        showscale=True, zmin=-1, zmax=1,
    ))
    fig_heat.update_layout(height=430, margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig_heat, width='stretch')

    # with col_rank:
    st.markdown("####  Corrélations avec l'AQI")
    aqi_corr = corr["pol_avg_aqi"].drop("pol_avg_aqi").sort_values(key=abs, ascending=False)
    for var, val in aqi_corr.items():
        bar_col = "#ef233c" if val > 0 else "#3a86ff"
        bar_w   = abs(val) * 100
        strength = "Forte" if abs(val) > 0.65 else "Modérée" if abs(val) > 0.35 else "Faible"
        icon     = "🔺" if val > 0 else "🔻"
        st.markdown(f"""
        <div style="background:#f8f9fa;border-radius:8px;padding:8px 12px;margin:5px 0;border-left:4px solid {bar_col}">
            <b>{lab_map[var]}</b>
            <span style="float:right;font-size:0.8rem;color:{bar_col}">{icon} {val:.3f} — {strength}</span>
            <div class="corr-bar" style="background:{bar_col};width:{bar_w}%;opacity:0.5"></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("####  Nuage de Points Bi-Varié")
    sc1, sc2, sc3 = st.columns([1,1,1])
    with sc1: x_var = st.selectbox("Variable X", NUM_COLS, index=5, format_func=lambda x: lab_map[x])
    with sc2: y_var = st.selectbox("Variable Y", NUM_COLS, index=0, format_func=lambda x: lab_map[x])
    with sc3: color_var = st.selectbox("Couleur", ["city"] + NUM_COLS, format_func=lambda x: x if x == "city" else lab_map[x])

    fig_sc = px.scatter(
        df_c, x=x_var, y=y_var,
        color=color_var,
        trendline="ols",
        labels={x_var: lab_map[x_var], y_var: lab_map[y_var]},
        hover_data=["city","date"],
        color_continuous_scale="Viridis" if color_var != "city" else None,
    )
    r_val = corr.loc[x_var, y_var] if x_var in corr.index and y_var in corr.columns else 0
    fig_sc.update_layout(height=380, title=f"r = {r_val:.3f}  |  {lab_map[x_var]} vs {lab_map[y_var]}", margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_sc, width='stretch')


    # # Time-series multi-city comparison
    # st.markdown("---")
    # st.markdown("#### 📊 Comparaison Temporelle Multi-Villes")
    # comp_cities = st.multiselect("Villes", sorted(df_main["city"].unique()), default=["Paris","Bordeaux","Lille"])
    # comp_metric = st.selectbox("Indicateur", NUM_COLS, format_func=lambda x: lab_map[x])

    # fig_ts = go.Figure()
    # clrs = ["#4361ee","#ef233c","#06d6a0","#fb8500","#8338ec","#3a86ff","#ff006e","#ffbe0b"]
    # for i, city in enumerate(comp_cities):
    #     df_tc = df_main[df_main["city"] == city].sort_values("date")
    #     fig_ts.add_trace(go.Scatter(x=df_tc["date"], y=df_tc[comp_metric], name=city,
    #         mode="lines+markers", line=dict(color=clrs[i % len(clrs)], width=2)))
    # fig_ts.update_layout(height=340, title=f"Évolution : {lab_map[comp_metric]}",
    #     xaxis_title="Date", yaxis_title=lab_map[comp_metric],
    #     legend=dict(orientation="h"), margin=dict(l=20,r=20,t=50,b=20))
    # st.plotly_chart(fig_ts, width='stretch')

    # # Pair plot summary
    # st.markdown("---")
    # st.markdown("#### 🔢 Statistiques Descriptives")
    # st.dataframe(df_corr_data.describe().round(2).rename(columns=lab_map), width='stretch')