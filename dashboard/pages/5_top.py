import streamlit as st
import pandas as pd
from dashboard.shared import fetch_analytics, render_sidebar_filters

st.set_page_config(page_title="Топ", layout="wide")
st.title("🔥 Топ самых дорогих объектов")

render_sidebar_filters()

data_top = fetch_analytics("/api/analytics/top-expensive", "limit=10")
if isinstance(data_top, list) and data_top:
    df_top = pd.DataFrame(data_top)
    st.dataframe(df_top, hide_index=True, use_container_width=True)
    st.subheader("Цена за м² по объектам")
    st.bar_chart(df_top.set_index("canonical_address")["last_price_per_sqm"])
else:
    st.info("Нет данных")