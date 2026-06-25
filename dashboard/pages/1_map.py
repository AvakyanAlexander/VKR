import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from dashboard.shared import fetch_offers, get_filter_params, render_sidebar_filters

st.set_page_config(page_title="Карта", layout="wide")
st.title("🗺️ Тепловая карта цен")

render_sidebar_filters()

query_string = get_filter_params()
data = fetch_offers(query_string)
df = pd.DataFrame(data.get("offers", []))

st.sidebar.metric("Найдено объектов", data.get("count", 0))

if not df.empty and "latitude" in df.columns and "longitude" in df.columns:
    df_map = df.dropna(subset=["latitude", "longitude"])

    if not df_map.empty:
        center_lat = df_map["latitude"].mean()
        center_lon = df_map["longitude"].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

        df_grouped = (
            df_map.groupby(["latitude", "longitude"])
            .agg(
                count=("id", "count"),
                avg_price_sqm=("last_price_per_sqm", "mean"),
                min_price=("last_price", "min"),
                max_price=("last_price", "max"),
                addresses=("canonical_address", lambda x: list(x))
            )
            .reset_index()
        )

        if not df_grouped.empty:
            min_sqm = df_grouped["avg_price_sqm"].min()
            max_sqm = df_grouped["avg_price_sqm"].max()

            def get_color(price_sqm):
                if max_sqm == min_sqm:
                    return "#3388ff"
                ratio = (price_sqm - min_sqm) / (max_sqm - min_sqm)
                if ratio < 0.5:
                    r = int(255 * (ratio * 2))
                    g = 255
                else:
                    r = 255
                    g = int(255 * (2 - ratio * 2))
                return f"#{r:02x}{g:02x}00"

            for _, row in df_grouped.iterrows():
                addr_list = row["addresses"][:5]
                addr_text = "<br>".join(addr_list)
                if len(row["addresses"]) > 5:
                    addr_text += f"<br>... и ещё {len(row['addresses']) - 5}"

                popup_html = f"""
                <b>Объектов:</b> {row['count']}<br>
                <b>Средняя цена м²:</b> {row['avg_price_sqm']:,.0f} ₽<br>
                <b>Мин. цена:</b> {row['min_price']:,.0f} ₽<br>
                <b>Макс. цена:</b> {row['max_price']:,.0f} ₽<br>
                <hr>{addr_text}
                """
                radius = max(5, min(20, row["count"] * 3))

                folium.CircleMarker(
                    location=[row["latitude"], row["longitude"]],
                    radius=radius,
                    color=get_color(row["avg_price_sqm"]),
                    fill=True,
                    fill_color=get_color(row["avg_price_sqm"]),
                    fill_opacity=0.7,
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=f"{row['count']} об. | {row['avg_price_sqm']:,.0f} ₽/м²"
                ).add_to(m)

        st_folium(m, width=1200, height=600)
        st.caption("🟢 Дёшево → 🟡 Средне → 🔴 Дорого (по цене за м²)")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Объектов на карте", len(df_map))
        with col2:
            st.metric("Средняя цена за м²", f"{df_map['last_price_per_sqm'].mean():,.0f} ₽")
        with col3:
            st.metric("Средняя площадь", f"{df_map['area_total'].mean():,.1f} м²")
    else:
        st.warning("Нет объектов с координатами.")
else:
    st.info("Нет данных для отображения. Измените фильтры или запустите сбор данных.")