import streamlit as st
import pandas as pd
from dashboard.shared import fetch_analytics, render_sidebar_filters

st.set_page_config(page_title="Районы", layout="wide")
st.title("🏘️ Аналитика по районам")

render_sidebar_filters()

data_district = fetch_analytics("/api/analytics/price-by-district")
if isinstance(data_district, list) and data_district:
    df_district = pd.DataFrame(data_district)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Средняя цена по районам")
        st.bar_chart(df_district.set_index("district")["avg_price_sqm"])
    with col2:
        st.subheader("Количество объектов по районам")
        st.bar_chart(df_district.set_index("district")["count"])
else:
    st.info("Нет данных по районам")

st.subheader("Средняя цена по типу дома")
data_btype = fetch_analytics("/api/analytics/price-by-building-type")
if isinstance(data_btype, list) and data_btype:
    df_btype = pd.DataFrame(data_btype)
    st.bar_chart(df_btype.set_index("building_type")["avg_price_sqm"])
else:
    st.info("Нет данных по типам домов")