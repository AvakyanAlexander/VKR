from fastapi import FastAPI, Query
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
import importlib
import threading
from datetime import datetime

app = FastAPI(title="Real Estate Analytics API")

parse_logs = []
parse_status = {"running": False, "last_run": None}

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "VKR",
    "user": "Alexs",
    "password": "root"
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@app.get("/api/offers")
def get_offers(
    limit: int = Query(500, le=2000),
    min_price: float = Query(None),
    max_price: float = Query(None),
    min_price_sqm: float = Query(None),
    max_price_sqm: float = Query(None),
    min_area: float = Query(None),
    max_area: float = Query(None),
    rooms: str = Query(None),       # строка "1,2,3" для фильтрации по нескольким значениям
    property_type: str = Query(None),
    building_type: str = Query(None),
    metro_station: str = Query(None),
    district: str = Query(None)
):
    """Список унифицированных объектов с расширенной фильтрацией."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    query = """
        SELECT id, canonical_address, area_total, area_kitchen, area_living,
               rooms, floor, floors_total,
               last_price, last_price_per_sqm,
               property_type, building_type, building_year,
               metro_station, metro_distance,
               last_seen_at, latitude, longitude
        FROM unified_objects
        WHERE status = 'active'
    """
    params = []
    conditions = []

    if min_price is not None:
        conditions.append("last_price >= %s")
        params.append(min_price)
    if max_price is not None:
        conditions.append("last_price <= %s")
        params.append(max_price)
    if min_price_sqm is not None:
        conditions.append("last_price_per_sqm >= %s")
        params.append(min_price_sqm)
    if max_price_sqm is not None:
        conditions.append("last_price_per_sqm <= %s")
        params.append(max_price_sqm)
    if min_area is not None:
        conditions.append("area_total >= %s")
        params.append(min_area)
    if max_area is not None:
        conditions.append("area_total <= %s")
        params.append(max_area)
    if rooms:
        rooms_list = [int(r.strip()) for r in rooms.split(",") if r.strip().isdigit()]
        if rooms_list:
            conditions.append("rooms IN ({})".format(",".join(["%s"] * len(rooms_list))))
            params.extend(rooms_list)
    if property_type:
        conditions.append("property_type = %s")
        params.append(property_type)
    if building_type:
        conditions.append("building_type = %s")
        params.append(building_type)
    if metro_station:
        conditions.append("metro_station ILIKE %s")
        params.append(f"%{metro_station}%")
    if district:
        conditions.append("canonical_address ILIKE %s")
        params.append(f"%{district}%")

    if conditions:
        query += " AND " + " AND ".join(conditions)

    query += " ORDER BY last_seen_at DESC LIMIT %s"
    params.append(limit)

    cursor.execute(query, params)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"count": len(results), "offers": results}


@app.get("/api/offers/{offer_id}")
def get_offer(offer_id: int):
    """Один объект + история цен."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT * FROM unified_objects WHERE id = %s", (offer_id,))
    offer = cursor.fetchone()

    if not offer:
        return {"error": "Not found"}

    cursor.execute("""
        SELECT source, price, price_per_sqm, date
        FROM price_history
        WHERE unified_object_id = %s
        ORDER BY date
    """, (offer_id,))
    history = cursor.fetchall()

    cursor.close()
    conn.close()
    return {"offer": offer, "price_history": history}


@app.get("/api/analytics/trends")
def get_trends(days: int = Query(30, le=365)):
    """Динамика средней цены за последние N дней."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT date, AVG(price) as avg_price, AVG(price_per_sqm) as avg_price_sqm
        FROM price_history
        WHERE date >= CURRENT_DATE - %s
        GROUP BY date
        ORDER BY date
    """, (days,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"days": days, "trends": results}
@app.get("/api/analytics/price-by-rooms")
def price_by_rooms():
    """Средняя цена по количеству комнат."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT rooms, 
               COUNT(*) as count,
               AVG(last_price_per_sqm) as avg_price_sqm
        FROM unified_objects
        WHERE status = 'active' 
          AND rooms IS NOT NULL
          AND rooms > 0
        GROUP BY rooms
        ORDER BY rooms
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

@app.get("/api/analytics/price-by-district")
def price_by_district():
    """Средняя цена по районам (из адреса)."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT 
            SPLIT_PART(canonical_address, ',', 3) as district,
            COUNT(*) as count,
            AVG(last_price_per_sqm) as avg_price_sqm
        FROM unified_objects
        WHERE status = 'active' AND canonical_address LIKE '%р-н%'
        GROUP BY district
        ORDER BY avg_price_sqm DESC
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

@app.get("/api/analytics/price-by-building-type")
def price_by_building_type():
    """Средняя цена по типу дома."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT building_type, 
               COUNT(*) as count,
               AVG(last_price_per_sqm) as avg_price_sqm
        FROM unified_objects
        WHERE status = 'active' 
          AND building_type IS NOT NULL
          AND building_type != ''
          AND building_type != '-'
        GROUP BY building_type
        ORDER BY avg_price_sqm DESC
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

@app.get("/api/analytics/summary")
def summary():
    """Общая сводка по рынку."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT 
            COUNT(*) as total_offers,
            AVG(last_price) as avg_price,
            AVG(last_price_per_sqm) as avg_price_sqm,
            MIN(last_price_per_sqm) as min_price_sqm,
            MAX(last_price_per_sqm) as max_price_sqm,
            AVG(area_total) as avg_area,
            AVG(rooms) as avg_rooms
        FROM unified_objects
        WHERE status = 'active'
    """)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

@app.get("/api/analytics/price-distribution")
def price_distribution():
    """Распределение объектов по ценовым сегментам."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT 
            CASE 
                WHEN last_price_per_sqm < 200000 THEN '< 200 тыс.'
                WHEN last_price_per_sqm < 400000 THEN '200-400 тыс.'
                WHEN last_price_per_sqm < 600000 THEN '400-600 тыс.'
                WHEN last_price_per_sqm < 800000 THEN '600-800 тыс.'
                WHEN last_price_per_sqm < 1000000 THEN '800 тыс. - 1 млн.'
                ELSE '> 1 млн.'
            END as price_range,
            COUNT(*) as count
        FROM unified_objects
        WHERE status = 'active' AND last_price_per_sqm IS NOT NULL
        GROUP BY price_range
        ORDER BY MIN(last_price_per_sqm)
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

@app.get("/api/analytics/top-expensive")
def top_expensive(limit: int = Query(10, le=50)):
    """Топ самых дорогих объектов по цене за м²."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT canonical_address, rooms, area_total, 
               last_price, last_price_per_sqm, metro_station
        FROM unified_objects
        WHERE status = 'active'
        ORDER BY last_price_per_sqm DESC NULLS LAST
        LIMIT %s
    """, (limit,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def run_parser_thread(source: str, pages: int):
    """Запускает парсер в отдельном потоке и собирает логи."""
    global parse_logs, parse_status

    try:
        parse_status["running"] = True
        parse_status["progress"] = f"Парсинг {source}..."
        parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск парсера {source} ({pages} стр.)...")

        if source == "cian":
            from Cian.cianparserfin import  run_parser as cian_run
            result = cian_run(pages)
            parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Циан: собрано {result} объявлений")
        elif source == "avito":
            from avito_parser import get_data_from_offers as avito_run
            df = avito_run()
            parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Авито: собрано {len(df)} объявлений")
        else:
            parse_logs.append(f"❌ Неизвестный источник: {source}")

    except Exception as e:
        parse_logs.append(f"❌ Ошибка: {str(e)}")
        import traceback
        parse_logs.append(traceback.format_exc()[-300:])
    finally:
        parse_status["running"] = False
        parse_status["progress"] = "Готово"
        parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Завершено.")


@app.post("/api/parse/start")
def start_parsing(source: str = "cian", pages: int = 1):
    global parse_status

    if parse_status["running"]:
        return {"error": "Парсинг уже запущен. Дождитесь завершения."}

    parse_logs.clear()
    parse_status["last_run"] = datetime.now().isoformat()

    # Запускаем в отдельном потоке, чтобы не блокировать API
    thread = threading.Thread(target=run_parser_thread, args=(source, pages), daemon=True)
    thread.start()

    return {"status": "started", "message": f"Парсинг {source} запущен в фоне"}


@app.get("/api/parse/status")
def parse_status_endpoint():
    return {
        "running": parse_status["running"],
        "progress": parse_status["progress"],
        "last_run": parse_status["last_run"],
        "logs": parse_logs[-30:]
    }

if __name__ == "__main__":
    uvicorn.run("api:app", reload=True)