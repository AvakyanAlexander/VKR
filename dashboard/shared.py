import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"


@st.cache_data(ttl=60)
def fetch_offers(params_json: str):
    """Запрос к /api/offers с кэшированием."""
    response = requests.get(f"{API_URL}/api/offers?{params_json}")
    if response.ok:
        return response.json()
    return {"count": 0, "offers": []}


@st.cache_data(ttl=300)
def fetch_analytics(endpoint: str, params: str = ""):
    """Универсальный запрос к аналитическим эндпоинтам."""
    url = f"{API_URL}{endpoint}"
    if params:
        url += f"?{params}"
    response = requests.get(url)
    if response.ok:
        return response.json()
    return {}


@st.cache_data(ttl=60)
def fetch_parse_status():
    """Запрос статуса парсинга."""
    response = requests.get(f"{API_URL}/api/parse/status")
    if response.ok:
        return response.json()
    return {"running": False, "logs": []}


def get_filter_params() -> str:
    """Возвращает строку query-параметров из session_state."""
    params = {
        "limit": 1000,
        "min_price": st.session_state.get("min_price", 0) if st.session_state.get("min_price", 0) > 0 else None,
        "max_price": st.session_state.get("max_price", 100_000_000) if st.session_state.get("max_price", 100_000_000) < 100_000_000 else None,
        "min_price_sqm": st.session_state.get("min_sqm", 0) if st.session_state.get("min_sqm", 0) > 0 else None,
        "max_price_sqm": st.session_state.get("max_sqm", 2_000_000) if st.session_state.get("max_sqm", 2_000_000) < 2_000_000 else None,
        "min_area": st.session_state.get("min_area", 0) if st.session_state.get("min_area", 0) > 0 else None,
        "max_area": st.session_state.get("max_area", 500) if st.session_state.get("max_area", 500) < 500 else None,
        "rooms": st.session_state.get("rooms_param"),
        "building_type": st.session_state.get("building_type") if st.session_state.get("building_type") else None,
        "district": st.session_state.get("district") if st.session_state.get("district") else None,
        "metro_station": st.session_state.get("metro") if st.session_state.get("metro") else None,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return "&".join(f"{k}={v}" for k, v in params.items())


def render_sidebar_filters():
    """Рисует боковую панель фильтров на всех страницах."""
    st.sidebar.header("🔍 Фильтры")

    st.sidebar.subheader("Цена (руб.)")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.number_input("От", value=0, step=1_000_000, key="min_price")
    with col2:
        st.number_input("До", value=100_000_000, step=1_000_000, key="max_price")

    st.sidebar.subheader("Цена за м² (руб.)")
    col3, col4 = st.sidebar.columns(2)
    with col3:
        st.number_input("От", value=0, step=50_000, key="min_sqm")
    with col4:
        st.number_input("До", value=2_000_000, step=50_000, key="max_sqm")

    st.sidebar.subheader("Площадь (м²)")
    col5, col6 = st.sidebar.columns(2)
    with col5:
        st.number_input("От", value=0, step=10, key="min_area")
    with col6:
        st.number_input("До", value=500, step=10, key="max_area")

    st.sidebar.subheader("Количество комнат")
    rooms_options = st.sidebar.multiselect(
        "Выберите",
        options=[0, 1, 2, 3, 4, 5, 6],
        default=[],
        key="rooms_multiselect",
        format_func=lambda x: "Студия" if x == 0 else str(x)
    )
    st.session_state["rooms_param"] = ",".join(str(r) for r in rooms_options) if rooms_options else None

    st.sidebar.subheader("Тип дома")
    st.sidebar.selectbox(
        "Выберите",
        options=["", "монолитный", "монолитно-кирпичный", "кирпичный", "панельный", "блочный"],
        key="building_type",
        format_func=lambda x: "Все" if x == "" else x
    )

    st.sidebar.subheader("Район")
    st.sidebar.text_input("Название района", key="district", placeholder="Например: Пресненский")

    st.sidebar.subheader("Метро")
    st.sidebar.text_input("Станция метро", key="metro", placeholder="Например: Павелецкая")

    if st.sidebar.button("🔄 Сбросить фильтры", use_container_width=True):
        keys_to_clear = [
            "min_price", "max_price", "min_sqm", "max_sqm",
            "min_area", "max_area", "rooms_multiselect",
            "building_type", "district", "metro", "rooms_param"
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        st.cache_data.clear()
        st.rerun()