import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import folium_static

API_URL = "http://api:8000"

st.set_page_config(page_title="Аналитика рынка недвижимости", layout="wide")
st.title("Аналитика рынка недвижимости")

# ============================================================
# Боковая панель: ФИЛЬТРЫ
# ============================================================
st.sidebar.header("Фильтры")

# Цена общая
st.sidebar.subheader("Цена (руб.)")
col1, col2 = st.sidebar.columns(2)
with col1:
    min_price = st.number_input("От", value=0, step=1000000, key="min_price")
with col2:
    max_price = st.number_input("До", value=100000000, step=1000000, key="max_price")

# Цена за м²
st.sidebar.subheader("Цена за м² (руб.)")
col3, col4 = st.sidebar.columns(2)
with col3:
    min_price_sqm = st.number_input("От", value=0, step=50000, key="min_sqm")
with col4:
    max_price_sqm = st.number_input("До", value=2000000, step=50000, key="max_sqm")

# Площадь
st.sidebar.subheader("Площадь (м²)")
col5, col6 = st.sidebar.columns(2)
with col5:
    min_area = st.number_input("От", value=0, step=10, key="min_area")
with col6:
    max_area = st.number_input("До", value=500, step=10, key="max_area")

# Комнаты
st.sidebar.subheader("Количество комнат")
rooms_options = st.sidebar.multiselect(
    "Выберите",
    options=[0,1, 2, 3, 4, 5, 6],
    default=[],
    format_func=lambda x: "Студия" if x == 0 else str(x)
)
rooms_param = ",".join(str(r) for r in rooms_options) if rooms_options else None

# Тип дома
st.sidebar.subheader("Тип дома")
building_type = st.sidebar.selectbox(
    "Выберите",
    options=["","монолитный", "монолитно-кирпичный", "кирпичный", "панельный", "блочный"],
    format_func=lambda x: "Все" if x == "" else x
)

# Район
st.sidebar.subheader("Район")
district = st.sidebar.text_input("Название района", placeholder="Например: Пресненский")

# Метро
st.sidebar.subheader("Метро")
metro = st.sidebar.text_input("Станция метро", placeholder="Например: Павелецкая")

# Кнопка "Применить"
apply = st.sidebar.button("Применить фильтры", use_container_width=True)
# Кнопка "Сбросить фильтры"
if st.sidebar.button("Сбросить фильтры", use_container_width=True):
    # Очищаем кэш и перезагружаем страницу
    st.cache_data.clear()
    # Используем query_params для сброса
    st.query_params.clear()
    st.rerun()

# ============================================================
# Загрузка данных с фильтрами
# ============================================================
params = {
    "limit": 1000,
    "min_price": min_price if min_price > 0 else None,
    "max_price": max_price if max_price < 100000000 else None,
    "min_price_sqm": min_price_sqm if min_price_sqm > 0 else None,
    "max_price_sqm": max_price_sqm if max_price_sqm < 2000000 else None,
    "min_area": min_area if min_area > 0 else None,
    "max_area": max_area if max_area < 500 else None,
    "rooms": rooms_param,
    "building_type": building_type if building_type else None,
    "district": district if district else None,
    "metro_station": metro if metro else None,
}
# Убираем None-параметры
params = {k: v for k, v in params.items() if v is not None}

query_string = "&".join(f"{k}={v}" for k, v in params.items())
response = requests.get(f"{API_URL}/api/offers?{query_string}")

if response.ok:
    data = response.json()
    offers = data["offers"]
    df = pd.DataFrame(offers)

    st.sidebar.metric("Найдено объектов", data["count"])

    # ============================================================
    # Вкладки
    # ============================================================
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Карта", "Цены по комнатам", "Районы", "Таблица", "Топ", "Сбор"
    ])

# ============================================================
# Вкладка 1: КАРТА
# ============================================================
with tab1:
    st.header("Тепловая карта цен")

    if not df.empty and "latitude" in df.columns and "longitude" in df.columns:
        # Убираем строки без координат
        df_map = df.dropna(subset=["latitude", "longitude"])

        if not df_map.empty:
            center_lat = df_map["latitude"].mean()
            center_lon = df_map["longitude"].mean()

            m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

            # Группировка по координатам (объекты в одном доме)
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
                    """Цвет от зелёного (дёшево) до красного (дорого)."""
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
                    <hr>
                    {addr_text}
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

            folium_static(m, width=1200, height=600)

            # Легенда
            st.caption("🟢 Дёшево → 🟡 Средне → 🔴 Дорого (по цене за м²)")

            # Статистика по отфильтрованным объектам
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Объектов на карте", len(df_map))
            with col2:
                st.metric("Средняя цена за м²", f"{df_map['last_price_per_sqm'].mean():,.0f} ₽")
            with col3:
                st.metric("Средняя площадь", f"{df_map['area_total'].mean():,.1f} м²")
        else:
            st.warning("Нет объектов с координатами. Попробуйте изменить фильтры.")
    else:
        st.info("Загрузите данные или измените фильтры, чтобы увидеть объекты на карте.")

# ============================================================
# Вкладка 2: ЦЕНЫ ПО КОМНАТАМ
# ============================================================
with tab2:
    st.header("Средняя цена по количеству комнат")

    col1, col2 = st.columns(2)

    with col1:
        resp = requests.get(f"{API_URL}/api/analytics/price-by-rooms")
        if resp.ok:
            df_rooms = pd.DataFrame(resp.json())
            if not df_rooms.empty:
                st.bar_chart(df_rooms.set_index("rooms")["avg_price_sqm"])
                st.caption("Средняя цена за м² по количеству комнат")

    with col2:
        resp = requests.get(f"{API_URL}/api/analytics/price-distribution")
        if resp.ok:
            df_dist = pd.DataFrame(resp.json())
            if not df_dist.empty:
                st.bar_chart(df_dist.set_index("price_range")["count"])
                st.caption("Распределение объектов по ценовым сегментам")

    # График динамики
    st.subheader("Динамика средней цены")
    resp = requests.get(f"{API_URL}/api/analytics/trends?days=30")
    if resp.ok:
        df_trends = pd.DataFrame(resp.json()["trends"])
        if not df_trends.empty:
            st.line_chart(df_trends.set_index("date")["avg_price_sqm"])

# ============================================================
# Вкладка 3: РАЙОНЫ
# ============================================================
with tab3:
    st.header("Аналитика по районам")

    resp = requests.get(f"{API_URL}/api/analytics/price-by-district")
    if resp.ok:
        df_district = pd.DataFrame(resp.json())
        if not df_district.empty:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Средняя цена по районам")
                st.bar_chart(df_district.set_index("district")["avg_price_sqm"])

            with col2:
                st.subheader("Количество объектов по районам")
                st.bar_chart(df_district.set_index("district")["count"])

    resp = requests.get(f"{API_URL}/api/analytics/price-by-building-type")
    if resp.ok:
        df_btype = pd.DataFrame(resp.json())
        if not df_btype.empty:
            st.subheader("Средняя цена по типу дома")
            st.bar_chart(df_btype.set_index("building_type")["avg_price_sqm"])

# ============================================================
# Вкладка 4: ТАБЛИЦА
# ============================================================
with tab4:
    st.header("Все объекты")

    response = requests.get(f"{API_URL}/api/offers?limit=500")
    if response.ok:
        df = pd.DataFrame(response.json()["offers"])
        display_cols = [
            "id", "canonical_address", "rooms", "area_total",
            "last_price", "last_price_per_sqm", "metro_station",
            "building_type", "last_seen_at"
        ]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[display_cols], hide_index=True, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Скачать CSV", csv, "offers.csv", "text/csv")

# ============================================================
# Вкладка 5: ТОП
# ============================================================
with tab5:
    st.header("Топ самых дорогих объектов")

    resp = requests.get(f"{API_URL}/api/analytics/top-expensive?limit=10")
    if resp.ok:
        df_top = pd.DataFrame(resp.json())
        if not df_top.empty:
            st.dataframe(df_top, hide_index=True, use_container_width=True)
            st.subheader("Цена за м² по объектам")
            st.bar_chart(df_top.set_index("canonical_address")["last_price_per_sqm"])
# ============================================================
# Вкладка 6: СБОР ДАННЫХ
# ============================================================
with tab6:
    st.header("Сбор данных")

    col1, col2, col3 = st.columns(3)

    with col1:
        source = st.selectbox(
            "Источник",
            options=["cian", "avito", "incom", "all"],
            format_func=lambda x: {
                "cian": "Циан",
                "avito": "Авито",
                "incom": "ИНКОМ",
                "all": "Все источники"
            }[x]
        )

    with col2:
        pages = st.number_input("Количество страниц", min_value=1, max_value=10, value=1)

    with col3:
        st.write("")  # отступ
        st.write("")
        start_button = st.button("Начать парсинг", type="primary", use_container_width=True)

    # Статус
    status_placeholder = st.empty()
    log_placeholder = st.empty()

    if start_button:
        with st.spinner(f"Парсинг {source} ({pages} стр.)... Ожидайте."):
            response = requests.post(
                f"{API_URL}/api/parse/start",
                params={"source": source, "pages": pages}
            )

        if response.ok:
            result = response.json()
            if "error" in result:
                st.error(result["error"])
            else:
                st.success("Парсинг завершён!")
                st.subheader("Логи выполнения:")
                for log in result.get("logs", []):
                    st.text(log)
        else:
            st.error("Не удалось запустить парсинг. Проверьте, что FastAPI запущен.")

    # Кнопка обновления статуса
    if st.button("Проверить статус"):
        response = requests.get(f"{API_URL}/api/parse/status")
        if response.ok:
            status = response.json()
            if status["running"]:
                st.warning("Парсинг выполняется...")
            elif status["last_run"]:
                st.info(f"Последний запуск: {status['last_run']}")
            if status.get("logs"):
                st.subheader("Последние логи:")
                for log in status["logs"]:
                    st.text(log)