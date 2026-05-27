import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly_calplot import calplot
import json
from datetime import datetime,timedelta
from typing import Any, Dict, List, Optional
from config.towns import FRENCH_TOWNS
# from Alerte_page import render_alerts_page
from BI.helpers_BI import get_aqi_color,get_aqi_label,get_temp_color,trend_icon,advisory_html,weather_condition_details,uvi_color,fmt,g
from BI.data_loader import load_hourly_period,load_agg_data,load_hourly_data
from data_gen import fill_df_agg

## ajouter gestions des session states pour garder les filtres actifs entre les pages (villes)
## ajouter cache pour les données agrégées (par date) pour éviter de recharger à chaque changement de filtre (date)

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
    .kpi-val { font-size: 2rem; font-weight: 800; }
    .kpi-minmax { font-size: 1rem; gap: 0.8rem; }
    .kpi-min { font-size: 1.2rem;}
    .kpi-max { font-size: 1.2rem;}
    .kpi-lbl { font-size: 1rem; margin-top: 2px; }
    .advisory-ok     { background:#d4edda; border-left:5px solid #28a745; border-radius:10px; padding:1rem; color:#155724; margin:0.8rem 0; }
    .advisory-warn   { background:#fff3cd; border-left:5px solid #ffc107; border-radius:10px; padding:1rem; color:#856404; margin:0.8rem 0; }
    .advisory-danger { background:#f8d7da; border-left:5px solid #dc3545; border-radius:10px; padding:1rem; color:#721c24; margin:0.8rem 0; }
    .alert-row { border-radius:10px; padding:0.7rem 1rem; margin:0.4rem 0; display:flex; align-items:center; gap:12px; }
    .alert-critical { background:#fde8e8; border-left:4px solid #dc3545; }
    .alert-high     { background:#fff4e6; border-left:4px solid #f77f00; }
    .corr-bar { height:8px; border-radius:4px; margin-top:4px; }
</style>
""", unsafe_allow_html=True)

CITIES_COORDS = {
    town.name: {"lat": town.lat, "lon": town.lon}
    for town in FRENCH_TOWNS
}

st.set_page_config(
        page_title="KPI historique",
        layout="wide",
    )

st.markdown('<div class="main-header">📊 KPI historiques Qualité de l\'Air & Météo</div>', unsafe_allow_html=True)
# st.markdown(f'<div class="sub-header">Données du <b>{date_range}</b>  Survolez une ville pour tous les détails</div>', unsafe_allow_html=True)

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
        if selected_saison == "Hiver":
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
df_agg = fill_df_agg(df_agg,end_date = "2028-05-05")

if df_agg.empty:
            st.info(f"Pas de données pour la période sélectionnée")
else : 
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
    
    if df_city.empty :
        st.warning("Aucune donnée pour cette sélection.")
        st.stop()

    # # fake data
    # df_city = fill_df_agg(df_city,end_date = "2027-05-05")
    # st.dataframe(df_city)
    
    # ── KPI Row ──
    st.markdown("###  Indicateurs Clés")
    k = st.columns(5)
    def kpi(col, val, label,val_min = None,val_max=None, bg_color="#6f83f2"):
        
        minmax_html = ""
        if val_min is not None or val_max is not None:
            minmax_html = f"""
            <div class="kpi-minmax">
                <span class="kpi-min">min {val_min} |</span>
                <span class="kpi-max">max {val_max}</span>
            </div>
            """
        
        col.markdown(
        f'<div class="kpi-box" style="background: linear-gradient(135deg, {bg_color}cc, {bg_color});">'
        f'<div class="kpi-lbl">{label}</div>'
        f'<div class="kpi-val">{val}</div>'
        f'{minmax_html}'
        f'</div>',
        unsafe_allow_html=True
    )

    kpi(k[0], val=f"{df_city['pol_avg_aqi'].mean():.0f}",
        val_min=f"{df_city['pol_min_aqi'].mean():.0f}",
        val_max=f"{df_city['pol_max_aqi'].mean():.0f}",
        label= "🏭 AQI Moyen", bg_color=get_aqi_color(df_city['pol_avg_aqi'].mean()))
    kpi(k[1], f"{df_city['pol_avg_pm25'].mean():.0f}",
        val_min=f"{df_city['pol_avg_pm25'].min():.0f}",
        val_max=f"{df_city['pol_avg_pm25'].max():.0f}",   
        label="🔵 PM2.5",  bg_color = get_aqi_color(df_city['pol_avg_pm25'].mean()))
    kpi(k[2], f"{df_city['pol_avg_pm10'].mean():.0f}",
        val_min=f"{df_city['pol_avg_pm10'].min():.0f}",
        val_max=f"{df_city['pol_avg_pm10'].max():.0f}",   
        label = "🟡 PM10",  bg_color=get_aqi_color(df_city['pol_avg_pm10'].mean()))
    kpi(k[3], f"{df_city['pol_avg_no2'].mean():.0f}",
        val_min=f"{df_city['pol_avg_no2'].min():.0f}",
        val_max=f"{df_city['pol_avg_no2'].max():.0f}",     
        label = "🔴 NO₂",  bg_color=get_aqi_color(df_city['pol_avg_no2'].mean()))
    kpi(k[4], f"{df_city['pol_avg_o3'].mean():.0f}",
        val_min=f"{df_city['pol_avg_o3'].min():.0f}",
        val_max=f"{df_city['pol_avg_o3'].max():.0f}", 
        label="🟢 O3", bg_color=get_aqi_color(df_city['pol_avg_o3'].mean()))

    k2 = st.columns(5)
    kpi(k2[0], f"{df_city['w_avg_temperature'].mean():.1f}°C", 
        val_min=f"{df_city['w_min_temperature'].mean():.0f}",
        val_max=f"{df_city['w_max_temperature'].mean():.0f}" ,
        label="🌡️ Température", bg_color=get_temp_color(df_city['w_avg_temperature'].mean()))
    kpi(k2[1], f"{df_city['w_avg_humidity'].mean():.0f}%", 
        val_min=f"{df_city['w_avg_humidity'].min():.0f}",
        val_max=f"{df_city['w_avg_humidity'].max():.0f}" ,
        label="💧 Humidité",)
    kpi(k2[2], f"{df_city['w_avg_wind_speed'].mean():.1f} m/s", 
        val_min=f"{df_city['w_avg_wind_speed'].min():.0f}",
        val_max=f"{df_city['w_avg_wind_speed'].max():.0f}" , 
        label="💨 Vent")
    kpi(k2[3], f"{df_city['w_avg_uvi'].mean():.2f}", 
        val_min=f"{df_city['w_avg_uvi'].min():.0f}",
        val_max=f"{df_city['w_avg_uvi'].max():.0f}" ,
        label=" UV")
    kpi(k2[4], f"{df_city['w_avg_pressure'].mean():.2f}",  
        val_min=f"{df_city['w_avg_pressure'].min():.0f}",
        val_max=f"{df_city['w_avg_pressure'].max():.0f}" ,       
        label="⏲ Pression Atm.")




    # ── Charts ──
    st.markdown("---")
    st.markdown(f"####  Evolution journalière polluants — {selected_city}")
    st.markdown(f"")
    granularity_options = {
        "Période": ["Mois", "Année"],
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
    col_l, col_r = st.columns(2)
    

    # Définir les options de granularité selon le filtre actif

    #aqi/jour
    with col_l:
        # st.markdown("#### Évolution de l'AQI dans le temps")
        fig_aqi = go.Figure()
        fig_aqi.add_hrect(y0=0,   y1=50,  fillcolor="#00c853", opacity=0.2)
        fig_aqi.add_hrect(y0=50,  y1=100, fillcolor="#f9a825", opacity=0.2)
        fig_aqi.add_hrect(y0=100, y1=150, fillcolor="#ef6c00", opacity=0.2)
        fig_aqi.add_hrect(y0=150, y1=200, fillcolor="#e63131", opacity=0.2)
        fig_aqi.add_hrect(y0=200, y1=300, fillcolor="#6a1b9a", opacity=0.2)
        # fig_aqi.add_hrect(y0=300, y1=500, fillcolor="#6f0909", opacity=0.06)

        fig_aqi.add_trace(go.Scatter(x=df_city["date"], y=df_city["pol_max_aqi"], name="Max",
                                    hovertemplate=(
                                        "<b>%{x|%d %b %Y}</b><br>"
                                        "AQI : <b>%{y:.0f}</b><br>"
                                        "Min : <b>%{customdata[0]:.1f}</b><br>"
                                        "Max : <b>%{customdata[1]:.1f}</b><br>"
                                        "PM25 : <b>%{customdata[2]:.1f}</b> PM10 : <b>%{customdata[3]:.1f}</b><br>"
                                        "NO2 : <b>%{customdata[3]:.1f}</b>  O3 : <b>%{customdata[4]:.1f}</b><extra></extra>"
                                        # "O3 : <b>%{customdata[4]:.1f}</b><extra></extra>"
                                        ),
                                    customdata=df_city[["pol_min_aqi","pol_max_aqi","pol_avg_pm25",
                                                        "pol_avg_pm10","pol_avg_no2","pol_avg_o3"]].values,
                                    line=dict(color="#ef6c00", dash="dot", width=0.5)))
                                                        
        fig_aqi.add_trace(go.Scatter(x=df_city["date"], y=df_city["pol_min_aqi"], name="Min",
                                     hoverinfo="skip",fill='tonexty',fillcolor="rgba(239, 108, 0, 0.2)",
                                    line=dict(color="#00c853", dash="dot", width=0.5),
                                    ))
        
        fig_aqi.add_trace(go.Scatter(x=df_city["date"], y=df_city["pol_avg_aqi"], name="Moyenne",
                                    marker_color=df_city["pol_avg_aqi"].apply(get_aqi_color).to_list(),
                                    line=dict(color="black", dash="solid", width=1.5),
                                    hoverinfo="none",
                                    customdata=df_city[["pol_min_aqi","pol_max_aqi","pol_avg_pm25",
                                                        "pol_avg_pm10","pol_avg_no2","pol_avg_o3"]].values))
        
    
        pol = {"pol_avg_pm25" : "PM25", "pol_avg_pm10" : "PM10", "pol_avg_no2" : "no2", "pol_avg_o3" : "O₃"}       
        colors = ["#4895ef","orange","red","green"]
        for (col, label), color, idx in zip(pol.items(), colors, range(1, 5)):
            fig_aqi.add_trace(go.Scatter(
                x=df_city["date"], y=df_city[col].tolist(),
                mode="lines", 
                name=label,
                hoverinfo="skip",visible="legendonly",
                line=dict(width=2,color = color), marker=dict(size=7)
            ))   
            fig_aqi.add_trace(go.Bar(
                x=df_city["date"], y=df_city[col].tolist(),
                name=label,
                hoverinfo="skip",visible="legendonly",
            ))    
        
        
        
        fig_aqi.update_layout(
            
            hovermode="x",
            hoverdistance=100,
            xaxis=dict(rangeslider=dict(visible=True),type="date")
        )
        fig_aqi.update_xaxes(
            tickformat = "%b",
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikedash="dot"
        )
        fig_aqi.update_yaxes(
            range=[0, df_city["pol_max_aqi"].max()],  # De 0 à ta limite calculée
            title="Indice AQI",
            autorange=False,
        )
                
        
            # line=dict(color="#4361ee", width=2.5), fill="tozeroy", fillcolor="rgba(67,97,238,0.1)", mode="lines+markers"))
        # if city2:
        #     df_c2 = df_main[(df_main["city"] == city2) & (df_main["date"] >= d_start) & (df_main["date"] <= d_end)].sort_values("date")
        #     fig_aqi.add_trace(go.Scatter(x=df_c2["date"], y=df_c2["avg_aqi"], name=city2,
        #         line=dict(color="#f77f00", width=2, dash="dash"), mode="lines+markers"))
        fig_aqi.update_layout( title="Evolution AQI/jour",height=340, 
                              legend=dict(orientation="v", y=0.9), 
                              margin=dict(l=10,r=10,t=20,b=20), 
                              yaxis_title="AQI")
        st.plotly_chart(fig_aqi, width='stretch')

        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(x=df_city["date"], y=df_city["w_max_temperature"], name="Max",
                                    line=dict(color="#ef6c00", dash="dot", width=1.5),
                                    hovertemplate=(
                                        "<b>%{x}</b><br>"
                                        "Moy : <b>%{customdata[0]:.1f}</b><br>"
                                        "Max : <b>%{y:.1f}</b><br>"
                                        "Min : <b>%{customdata[1]:.1f}</b><extra></extra>"
                                        ),
                                    customdata=df_city[["w_avg_temperature","w_min_temperature"]].values))
                                #  ['solid', 'dot', 'dash', 'longdash', 'dashdot', 'longdashdot']                       
        fig_temp.add_trace(go.Scatter(x=df_city["date"], y=df_city["w_min_temperature"], name="Min",
                                     fill="tonexty",fillcolor="rgba(239, 108, 0, 0.2)",
                                     hoverinfo="skip",
                                    line=dict(color="#00c853", dash="dash", width=1.5)))
        
        
        fig_temp.update_layout(
            hovermode="x",
            hoverdistance=100
        )
        fig_temp.update_xaxes(
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikedash="dot"
        )
        # fig_temp.add_trace(go.Bar(x=df_city["date"], y=df_city["w_avg_temperature"], name="Moyenne",
        #                             marker_color=df_city["w_avg_temperature"].apply(get_temp_color).to_list(),
        #                             hovertemplate=(
        #                                 "<b>%{x}</b><br>"
        #                                 "T° : <b>%{y:.0f}</b><br>"
        #                                 "Min : <b>%{customdata[0]:.1f}</b><br>"
        #                                 "Max : <b>%{customdata[1]:.1f}</b><extra></extra>"
        #                                 ),
        #                                 customdata=df_city[["w_min_temperature","w_max_temperature"]].values))

        fig_temp.update_layout( title="Evolution Temp/jour",height=340, legend=dict(orientation="v", y=0.9), margin=dict(l=10,r=10,t=20,b=20), yaxis_title="AQI")
        st.plotly_chart(fig_temp, width='stretch')


    # polluants/jour
    # ── Granularité selon filter_mode 
    
    with col_r:

        # # Définir les options de granularité selon le filtre actif
        # granularity_options = {
        #     "Période": ["Jour", "Mois", "Année"],
        #     "Mois":    ["Jour"],
        #     "Saison":  ["Saison"],
        #     "Année":   ["Mois", "Année"],
        # }
        # options_dispo = granularity_options[filter_mode]

        # if len(options_dispo) > 1:
        #     granularity = st.segmented_control(
        #         "Granularité",
        #         options=options_dispo,
        #         default=options_dispo[0],
        #         key="granularity_pol"
        #     )
        # else:
        #     granularity = options_dispo[0]
        
        
        # ── Agrégation selon la granularité
        df_pol = df_city.copy()
        df_pol["date"] = pd.to_datetime(df_pol["date"])

        POL_COLS = ["pol_avg_aqi","pol_min_aqi","pol_max_aqi",
                    "pol_avg_pm25", "pol_avg_pm10", "pol_avg_no2", "pol_avg_o3",
                    "w_avg_temperature","w_min_temperature","w_max_temperature","w_avg_humidity",
                    "w_avg_pressure","w_avg_wind_speed","w_max_wind_gust"
                    ]
        

        # if granularity == "Jour":
        #     df_pol["x_label"] = df_pol["date"].dt.strftime("%d/%m/%Y")
        #     df_grouped = df_pol.groupby("x_label", sort=False)[POL_COLS].mean().reset_index()
        #     # Conserver l'ordre chronologique
        #     df_grouped = df_pol[["x_label"]].drop_duplicates().merge(df_grouped, on="x_label")

        if granularity == "Mois":
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
        
      
        # ── Figure 
        # st.dataframe(df_grouped)
        
        fig_aqi = go.Figure()
        fig_aqi.add_hrect(y0=0,   y1=50,  fillcolor="#00c853", opacity=0.1)
        fig_aqi.add_hrect(y0=50,  y1=100, fillcolor="#f9a825", opacity=0.1)
        fig_aqi.add_hrect(y0=100, y1=150, fillcolor="#ef6c00", opacity=0.1)
        fig_aqi.add_hrect(y0=150, y1=200, fillcolor="#e63131", opacity=0.1)
        fig_aqi.add_hrect(y0=200, y1=300, fillcolor="#6a1b9a", opacity=0.1)
        # fig_aqi.add_hrect(y0=300, y1=500, fillcolor="#6f0909", opacity=0.06)
        
        # Utilisation de Bar avec error_y pour représenter la plage Min/Max
        fig_aqi.add_trace(go.Bar(
            x=x_vals, y=df_grouped["pol_avg_aqi"],
            name="Moyenne",
            marker_color=df_grouped["pol_avg_aqi"].apply(get_aqi_color).to_list(),
            error_y=dict(
                type='data',
                symmetric=False,
                array=df_grouped["pol_max_aqi"] - df_grouped["pol_avg_aqi"],
                arrayminus=df_grouped["pol_avg_aqi"] - df_grouped["pol_min_aqi"]
            ),
            hovertemplate=(
                            "<b>%{x}</b><br>"
                            "AQI : <b>%{y:.0f}</b><br>"
                            "Min : <b>%{customdata[0]:.1f}</b><br>"
                            "Max : <b>%{customdata[1]:.1f}</b><br>"
                            "PM25 : <b>%{customdata[2]:.1f}</b> PM10 : <b>%{customdata[3]:.1f}</b><br>"
                            "NO2 : <b>%{customdata[3]:.1f}</b>  O3 : <b>%{customdata[4]:.1f}</b><extra></extra>"
                            # "O3 : <b>%{customdata[4]:.1f}</b><extra></extra>"
                            ),
                        customdata=df_city[["pol_min_aqi","pol_max_aqi","pol_avg_pm25",
                                            "pol_avg_pm10","pol_avg_no2","pol_avg_o3"]].values
        ))
        
        # Gestion des polluants (ajout dynamique)
        for (col, label), color in zip(pol.items(), colors):
            fig_aqi.add_trace(go.Bar(x=x_vals, y=df_grouped[col], name=label, 
                                marker_color=color,hoverinfo="none"))
                
                
        fig_aqi.update_layout(
            title=f"Évolution polluants / {granularity.lower()}",
            # height=340,
            barmode="group",
            legend=dict(orientation="v", y=1),
            # margin=dict(l=10, r=10, t=40, b=20),
            yaxis_title="AQi",
            xaxis_title=granularity,
            hovermode="x",
            hoverdistance=100,
            # xaxis=dict(rangeslider=dict(visible=True),type="date")
        )
        
        fig_aqi.update_xaxes(
            tickformat = "%b %Y",
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikedash="dot"
        )
        fig_aqi.update_yaxes(
            range=[0, df_city["pol_max_aqi"].max()],  # De 0 à ta limite calculée
            title="Indice AQI",
            autorange=False,
        )
        
        st.plotly_chart(fig_aqi,width='stretch')
        
        ## Tempe
        fig_TEMP = make_subplots(specs=[[{"secondary_y": True}]])
        fig_TEMP.add_trace(go.Bar(
            x=x_vals, y=df_grouped["w_avg_temperature"],
            name="Moyenne",
            marker_color=df_grouped["w_avg_temperature"].apply(get_temp_color).to_list(),
            error_y=dict(
                type='data',
                symmetric=False,
                array=df_grouped["w_max_temperature"] - df_grouped["w_avg_temperature"],
                arrayminus=df_grouped["w_avg_temperature"] - df_grouped["w_min_temperature"]
            ),
            hovertemplate=(
                            "<b>%{x}</b><br>"
                            "T° : <b>%{y:.0f}</b><br>"
                            "Humidité : <b>%{customdata[0]:.1f}</b><br>"
                            # "O3 : <b>%{customdata[4]:.1f}</b><extra></extra>"
                            ),
            customdata=df_city[["w_avg_humidity"]].values
            ),secondary_y=False)
        
        fig_TEMP.add_trace(go.Scatter(x=x_vals, y=df_grouped["w_avg_humidity"], name=label, 
                                marker_color="lightblue",hoverinfo="none"),secondary_y=True)
        st.plotly_chart(fig_TEMP,width='stretch')

        
        
       

    # ── Heatmaps
    st.markdown("---")
    st.markdown(f"#### Heatmap")
    # # Heatmap horaire multi-jours 

    heatmap_vars = {
        "Température (°C)":          "w_avg_temperature",
        "Humidité (%)":              "w_avg_humidity",
        "Vent moyen (m/s)":          "w_avg_wind_speed",
        "Rafales (m/s)":             "w_avg_wind_gust_mps",
        "Pression (hPa)":            "w_avg_pressure",
        "AQI":                       "pol_avg_aqi",
        "PM2.5":            "pol_avg_pm25",
        "PM10":             "pol_avg_pm10",
        "NO₂":              "pol_avg_no2",
        "O₃":               "pol_avg_o3",
    }
    heatmap_vars = {k: v for k, v in heatmap_vars.items() if v in df_pol.columns}

    hm_col1, hm_col2 = st.columns([2, 1])
    with hm_col1:
        hm_var_label = st.selectbox("Variable", list(heatmap_vars.keys()), key="hm_var")
    with hm_col2:
        
        palette = st.selectbox(
            "Palette",
            ["Blues", "temps", "thermal"],
            key="hm_palette",
        )
    
    def generate_colorscale(thresholds, colors, vmin=None, vmax=None):
        """
        Génère une colorscale Plotly à partir de seuils et couleurs.
        Si vmin/vmax ne sont pas fournis, on utilise les min/max des seuils.
        """
        if vmin is None: vmin = min(thresholds)
        if vmax is None: vmax = max(thresholds)
        
        scale = []
        prev_pos = 0
        
        for thr, col in zip(thresholds, colors):
            # Normalisation entre 0 et 1
            pos = (thr - vmin) / (vmax - vmin)
            
            # On ajoute les paires [position, couleur]
            # max(0, ...) et min(1, ...) sécurisent les dépassements
            scale.append([max(0, prev_pos), col])
            scale.append([min(1, pos), col])
            prev_pos = pos
            
        return scale
    
    aqi_scale = generate_colorscale(
    thresholds=[50, 100, 150, 200, 300],
    colors=["#00c853", "#f9a825", "#ef6c00", "#e63131", "#6a1b9a"],
    vmin=0, vmax=300)
    temp_scale = generate_colorscale(
    thresholds=[-15, -5, 0, 7, 14, 20, 25, 30, 35, 40],
    colors=["#4A148C", "#1565C0", "#42A5F5", "#81C784", "#CDDC39", 
            "#F5E33E", "#FBC02D", "#FB8C00", "#E53935", "#B71C1C"],
    vmin=-15,vmax=40
    )
    
    pol = ["AQI","PM2.5","PM10","NO₂","O₃"]
    hm_col = heatmap_vars[hm_var_label]
    fig = calplot(
        df_city, 
        x="date", 
        y= hm_col, 
        cmap_min=0 if hm_var_label in pol else -15 if hm_var_label == "Température (°C)" else None,
        cmap_max=300 if hm_var_label in pol else 40 if hm_var_label == "Température (°C)" else None,
        showscale=True,
        colorscale=aqi_scale if hm_var_label in pol else temp_scale if hm_var_label == "Température (°C)" else palette,
    )

    
    fig.update_layout(
            height=500,
            xaxis = dict(ticktext=["Jan","Fev","Mar","Apr","May","Jun","Jul",
                                    "Aug","Sep","Oct","Nov","Dec"]),
            yaxis = dict(ticktext=["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
            )
            )
    
    annees = sorted(df_pol["date"].dt.year.unique())
    yaxis_dict = {}
    for i, annee in enumerate(annees):
        key = "yaxis" if i == 0 else f"yaxis{i+1}"
        yaxis_dict[key] = {"title": str(annee)}

    fig.update_layout(yaxis_dict)
    
    st.plotly_chart(fig, use_container_width=True)
        

    
