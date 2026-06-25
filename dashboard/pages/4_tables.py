import streamlit as st
import pandas as pd
from dashboard.shared import fetch_offers, get_filter_params, render_sidebar_filters

st.set_page_config(page_title="Таблица", layout="wide")
st.title("📋 Все объекты")

render_sidebar_filters()

query_string = get_filter_params()
data = fetch_offers(query_string)
df = pd.DataFrame(data.get("offers", []))

st.sidebar.metric("Найдено объектов", data.get("count", 0))

if not df.empty:
    display_cols = [
        "id", "canonical_address", "rooms", "area_total",
        "last_price", "last_price_per_sqm", "metro_station",
        "building_type", "last_seen_at"
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[display_cols], hide_index=True, use_container_width=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Скачать CSV", csv, "offers.csv", "text/csv")
else:
    st.info("Нет данных для отображения.")