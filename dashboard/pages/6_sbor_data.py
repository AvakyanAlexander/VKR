import streamlit as st
import requests
from dashboard.shared import fetch_parse_status, API_URL

st.set_page_config(page_title="Сбор данных", layout="wide")
st.title("🕷️ Сбор данных")

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
    st.write("")
    st.write("")
    start_button = st.button("🚀 Начать парсинг", type="primary", use_container_width=True)

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
            st.success("✅ Парсинг запущен!")
            st.cache_data.clear()
    else:
        st.error("Не удалось запустить парсинг.")

if st.button("🔄 Проверить статус"):
    st.cache_data.clear()
    status = fetch_parse_status()
    if status.get("running"):
        st.warning("⏳ Парсинг выполняется...")
    elif status.get("last_run"):
        st.info(f"Последний запуск: {status['last_run']}")
    if status.get("logs"):
        st.subheader("📋 Последние логи:")
        for log in status["logs"]:
            st.text(log)