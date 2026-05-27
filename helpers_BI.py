# helpers BI
import streamlit as st
import pandas as pd
import numpy as np
import json
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo


def get_aqi_color(aqi):
    if pd.isna(aqi) or aqi == "N/A" : 
        return "#BEBABA"
    if aqi <= 50:  return "#00c853"
    if aqi <= 100: return "#f9a825"
    if aqi <= 150: return "#ef6c00"
    if aqi <= 200: return "#e63131"
    if aqi <= 300: return "#6a1b9a"
    return "#6f0909"

def get_aqi_label(aqi):
    if pd.isna(aqi) or aqi == "N/A": 
        return "N/A"
    else : 
        if aqi <= 50:  return "✅ Bon"
        if aqi <= 100: return "⚠️ Modéré"
        if aqi <= 150: return "🟠 Mauvais (sensibles)"
        if aqi <= 200: return "🔴 Mauvais"
        if aqi <= 300: return "🟣 Très Mauvais"
        return "⚫ Dangereux"

def get_temp_color(temp):
    if pd.isna(temp) or temp == "N/A" : 
        return "#BEBABA"
    if temp <= -15:  return "#4A148C"
    if temp <= -5: return "#1565C0"
    if temp <= 0: return "#42A5F5"
    if temp <= 7: return "#81C784"
    if temp <= 14: return "#CDDC39"
    if temp <= 20: return "#FFEB3B"
    if temp <= 25: return "#FBC02D"
    if temp <= 30: return "#FB8C00"
    if temp <= 35: return "#E53935"
    if temp <= 40: return "#B71C1C"
    return "#880E4F"

def trend_icon(t):
    return {"rising": "📈 Hausse", "falling": "📉 Baisse", "stable": "➡️ Stable"}.get(t, "➡️")

# page kpi : advise
def advisory_html(risk):
    if risk > 50 and risk <=150:
        return '<div class="advisory-warn">⚠️ <b>Précaution</b> — Sensibles (enfants, asthmatiques, personnes âgées) : limitez l\'exposition prolongée.</div>'
    if risk > 150 and risk <= 300:
         return '<div class="advisory-danger">🔴 <b>Alerte Santé</b> — Activités extérieures fortement déconseillées. Groupes sensibles : restez à l\'intérieur.</div>'
    if risk > 300 : 
        return '<div class="advisory-danger">☢️ <b>Danger sanitaire</b> — Restez en intérieur .</div>'
    return '<div class="advisory-ok">✅ <b>Conditions Satisfaisantes</b> — Qualité de l\'air acceptable. Activités normales possibles.</div>'


def weather_condition_details(
    feels_like,
    humidity,
    wind_speed,
    wind_gust=None,
    uvi=None
):
    severity_score = 0
    details = [] 
    
    if feels_like >= 45 or feels_like <= -25:
        severity_score += 4
        details.append("température dangeureuse")
    elif feels_like >= 38 or feels_like <= -15:
        severity_score += 3
        details.append("température extrême")
    elif feels_like >= 30 or feels_like <= -5:
        severity_score += 2
        details.append("température inconfortable")
    elif feels_like >= 27 or feels_like <= 5:
        severity_score += 1
        details.append("température légèrement inconfortable")
        
     # Very humid
    if humidity >= 85:
        severity_score += 2
        details.append("très forte humidité")
    elif humidity >= 70:
        severity_score += 1
        details.append("forte humidité")

    # Very dry
    elif humidity <= 15:
        severity_score += 2
        details.append("air très sec")
    elif humidity <= 25:
        severity_score += 1
        details.append("air sec")
    
    max_wind = wind_gust if wind_gust else wind_speed
    if max_wind >= 30:
        severity_score += 3
        details.append("vent violent")
    elif max_wind >= 20:
        severity_score += 2
        details.append("fort vent")
    elif max_wind >= 12:
        severity_score += 1
        details.append("venteux")
    
    if uvi is not None:
        if uvi >= 11:
            severity_score += 2
            details.append("UV extreme")
        elif uvi >= 8:
            severity_score += 1
            details.append("UV très élevé")
    
    if severity_score >= 9:
        level = "extreme"

    elif severity_score >= 6:
        level = "severe"

    elif severity_score >= 3:
        level = "moderate"

    else:
        level = "comfortable"

    return {
        "severity_score": severity_score,
        "level": level,
        "details": details,
    }

def uvi_color(val):
                if pd.isna(val):  return "#BEBABA"
                if val < 3:       return "#00c853"   # low
                if val < 6:       return "#f9a825"   # moderate
                if val < 8:       return "#ef6c00"   # high
                if val < 11:      return "#c62828"   # very high
                return "#6a0572"                     # extreme