import streamlit as st
import pandas as pd
from shared import fetch_analytics, render_sidebar_filters

st.set_page_config(page_title="Цены по комнатам", layout="wide")
st.title("📊 Средняя цена по количеству комнат")

render_sidebar_filters()

col1, col2 = st.columns(2)

with col1:
    data_rooms = fetch_analytics("/api/analytics/price-by-rooms")
    if isinstance(data_rooms, list) and data_rooms:
        df_rooms = pd.DataFrame(data_rooms)
        st.bar_chart(df_rooms.set_index("rooms")["avg_price_sqm"])
        st.caption("Средняя цена за м² по количеству комнат")
    else:
        st.info("Нет данных")

with col2:
    data_dist = fetch_analytics("/api/analytics/price-distribution")
    if isinstance(data_dist, list) and data_dist:
        df_dist = pd.DataFrame(data_dist)
        st.bar_chart(df_dist.set_index("price_range")["count"])
        st.caption("Распределение объектов по ценовым сегментам")
    else:
        st.info("Нет данных")

st.subheader("Динамика средней цены")
data_trends = fetch_analytics("/api/analytics/trends", "days=30")
if isinstance(data_trends, dict) and "trends" in data_trends:
    df_trends = pd.DataFrame(data_trends["trends"])
    if not df_trends.empty:
        st.line_chart(df_trends.set_index("date")["avg_price_sqm"])
        st.caption("Средняя цена за м² по дням")
    else:
        st.info("Недостаточно данных для отображения динамики.")