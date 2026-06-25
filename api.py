from fastapi import FastAPI, Query
import asyncpg
import uvicorn
import asyncio
import os
from datetime import datetime
import os

app = FastAPI(title="Real Estate Analytics API")

parse_logs = []
parse_status = {"running": False, "last_run": None}

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "VKR"),
    "user": os.getenv("POSTGRES_USER", "Alexs"),
    "password": os.getenv("POSTGRES_PASSWORD", "root")
}


async def get_connection():
    """Возвращает асинхронное соединение с БД."""
    return await asyncpg.connect(**DB_CONFIG)


@app.get("/api/offers")
async def get_offers(
    limit: int = Query(500, le=2000),
    min_price: float = Query(None),
    max_price: float = Query(None),
    min_price_sqm: float = Query(None),
    max_price_sqm: float = Query(None),
    min_area: float = Query(None),
    max_area: float = Query(None),
    rooms: str = Query(None),
    property_type: str = Query(None),
    building_type: str = Query(None),
    metro_station: str = Query(None),
    district: str = Query(None)
):
    """Список унифицированных объектов с расширенной фильтрацией."""
    conn = await get_connection()

    query = """
        SELECT id, canonical_address, area_total, area_kitchen, area_living,
               rooms, floor, floors_total,
               last_price, last_price_per_sqm,
               property_type, building_type, build_year,
               metro_station, metro_distance,
               last_seen_at, latitude, longitude
        FROM unified_objects
        WHERE status = 'active'
    """
    params = []
    conditions = []
    param_idx = 1

    if min_price is not None:
        conditions.append(f"last_price >= ${param_idx}")
        params.append(min_price)
        param_idx += 1
    if max_price is not None:
        conditions.append(f"last_price <= ${param_idx}")
        params.append(max_price)
        param_idx += 1
    if min_price_sqm is not None:
        conditions.append(f"last_price_per_sqm >= ${param_idx}")
        params.append(min_price_sqm)
        param_idx += 1
    if max_price_sqm is not None:
        conditions.append(f"last_price_per_sqm <= ${param_idx}")
        params.append(max_price_sqm)
        param_idx += 1
    if min_area is not None:
        conditions.append(f"area_total >= ${param_idx}")
        params.append(min_area)
        param_idx += 1
    if max_area is not None:
        conditions.append(f"area_total <= ${param_idx}")
        params.append(max_area)
        param_idx += 1
    if rooms:
        rooms_list = [int(r.strip()) for r in rooms.split(",") if r.strip().isdigit()]
        if rooms_list:
            placeholders = ", ".join([f"${param_idx + i}" for i in range(len(rooms_list))])
            conditions.append(f"rooms IN ({placeholders})")
            params.extend(rooms_list)
            param_idx += len(rooms_list)
    if property_type:
        conditions.append(f"property_type = ${param_idx}")
        params.append(property_type)
        param_idx += 1
    if building_type:
        conditions.append(f"building_type = ${param_idx}")
        params.append(building_type)
        param_idx += 1
    if metro_station:
        conditions.append(f"metro_station ILIKE ${param_idx}")
        params.append(f"%{metro_station}%")
        param_idx += 1
    if district:
        conditions.append(f"canonical_address ILIKE ${param_idx}")
        params.append(f"%{district}%")
        param_idx += 1

    if conditions:
        query += " AND " + " AND ".join(conditions)

    query += f" ORDER BY last_seen_at DESC LIMIT ${param_idx}"
    params.append(limit)

    results = await conn.fetch(query, *params)
    await conn.close()

    offers = [dict(row) for row in results]
    return {"count": len(offers), "offers": offers}


@app.get("/api/offers/{offer_id}")
async def get_offer(offer_id: int):
    """Один объект + история цен."""
    conn = await get_connection()

    offer = await conn.fetchrow("SELECT * FROM unified_objects WHERE id = $1", offer_id)

    if not offer:
        await conn.close()
        return {"error": "Not found"}

    history = await conn.fetch("""
        SELECT source, price, price_per_sqm, date
        FROM price_history
        WHERE unified_object_id = $1
        ORDER BY date
    """, offer_id)

    await conn.close()

    return {
        "offer": dict(offer),
        "price_history": [dict(row) for row in history]
    }


@app.get("/api/analytics/trends")
async def get_trends(days: int = Query(30, le=365)):
    """Динамика средней цены за последние N дней."""
    conn = await get_connection()
    results = await conn.fetch("""
        SELECT date, AVG(price) as avg_price, AVG(price_per_sqm) as avg_price_sqm
        FROM price_history
        WHERE date >= CURRENT_DATE - $1::integer
        GROUP BY date
        ORDER BY date
    """, days)
    await conn.close()
    return {"days": days, "trends": [dict(row) for row in results]}


@app.get("/api/analytics/price-by-rooms")
async def price_by_rooms():
    """Средняя цена по количеству комнат."""
    conn = await get_connection()
    results = await conn.fetch("""
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
    await conn.close()
    return [dict(row) for row in results]


@app.get("/api/analytics/price-by-district")
async def price_by_district():
    """Средняя цена по районам (из адреса)."""
    conn = await get_connection()
    results = await conn.fetch("""
        SELECT 
            SPLIT_PART(canonical_address, ',', 3) as district,
            COUNT(*) as count,
            AVG(last_price_per_sqm) as avg_price_sqm
        FROM unified_objects
        WHERE status = 'active' AND canonical_address LIKE '%р-н%'
        GROUP BY district
        ORDER BY avg_price_sqm DESC
    """)
    await conn.close()
    return [dict(row) for row in results]


@app.get("/api/analytics/price-by-building-type")
async def price_by_building_type():
    """Средняя цена по типу дома."""
    conn = await get_connection()
    results = await conn.fetch("""
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
    await conn.close()
    return [dict(row) for row in results]


@app.get("/api/analytics/summary")
async def summary():
    """Общая сводка по рынку."""
    conn = await get_connection()
    result = await conn.fetchrow("""
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
    await conn.close()
    return dict(result)


@app.get("/api/analytics/price-distribution")
async def price_distribution():
    """Распределение объектов по ценовым сегментам."""
    conn = await get_connection()
    results = await conn.fetch("""
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
    await conn.close()
    return [dict(row) for row in results]


@app.get("/api/analytics/top-expensive")
async def top_expensive(limit: int = Query(10, le=50)):
    """Топ самых дорогих объектов по цене за м²."""
    conn = await get_connection()
    results = await conn.fetch("""
        SELECT canonical_address, rooms, area_total, 
               last_price, last_price_per_sqm, metro_station
        FROM unified_objects
        WHERE status = 'active'
        ORDER BY last_price_per_sqm DESC NULLS LAST
        LIMIT $1
    """, limit)
    await conn.close()
    return [dict(row) for row in results]


import threading

def run_parser_in_thread(source: str, pages: int):
    """Запускает парсер в отдельном потоке с новым event loop."""
    global parse_logs, parse_status

    async def _run():
        try:
            parse_status["running"] = True
            parse_status["progress"] = f"Парсинг {source}..."
            parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск парсера {source} ({pages} стр.)...")

            total_collected = 0

            if source == "cian":
                import sys
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cian"))
                from Cian.cianparserPlaywrigthTest import run_parser as cian_run
                result = await cian_run(pages)
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Циан: собрано {result} объявлений")
                total_collected = result

            elif source == "avito":
                from Avito.avitoparserPlaywrigthMaska import get_data_from_offers as avito_run
                df = avito_run()
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Авито: собрано {len(df)} объявлений")
                total_collected = len(df)

            elif source == "incom":
                from INCOM.Incomparserplaywrigth import run_parser as incom_run
                result = await incom_run(pages)
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ИНКОМ: собрано {result} объявлений")
                total_collected = result

            elif source == "all":
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Последовательный запуск трёх парсеров...")

                import sys
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cian"))
                from Cian.cianparserPlaywrigthTest import run_parser as cian_run
                from INCOM.Incomparserplaywrigth import run_parser as incom_run

                # Циан
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск Циан...")
                cian_result = await cian_run(pages)
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Циан: собрано {cian_result} объявлений")
                total_collected += cian_result

                # Авито
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск Авито...")
                from Avito.avitoparserPlaywrigthMaska import get_data_from_offers as avito_run
                df = avito_run()
                avito_result = len(df)
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Авито: собрано {avito_result} объявлений")
                total_collected += avito_result

                # ИНКОМ
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск ИНКОМ...")
                incom_result = await incom_run(pages)
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ИНКОМ: собрано {incom_result} объявлений")
                total_collected += incom_result

            else:
                parse_logs.append(f"❌ Неизвестный источник: {source}")
                return

            # === Запуск дедупликации после парсинга ===
            if total_collected > 0:
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск дедупликации...")
                from etl_deduplicate import run_deduplication as run_dedup
                run_dedup()
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Дедупликация завершена")
            else:
                parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Дедупликация не требуется (нет новых записей)")

        except Exception as e:
            parse_logs.append(f"❌ Ошибка: {str(e)}")
            import traceback
            parse_logs.append(traceback.format_exc()[-500:])
        finally:
            parse_status["running"] = False
            parse_status["progress"] = "Готово"
            parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Завершено.")
            parse_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Всего собрано: {total_collected} объявлений")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except:
            pass
        finally:
            loop.close()


@app.post("/api/parse/start")
async def start_parsing(source: str = "cian", pages: int = 1):
    global parse_status

    if parse_status["running"]:
        return {"error": "Парсинг уже запущен. Дождитесь завершения."}

    parse_logs.clear()
    parse_status["last_run"] = datetime.now().isoformat()

    # Запускаем в отдельном потоке с новым event loop
    thread = threading.Thread(target=run_parser_in_thread, args=(source, pages), daemon=True)
    thread.start()

    return {"status": "started", "message": f"Парсинг {source} запущен в фоне"}


@app.get("/api/parse/status")
def parse_status_endpoint():
    return {
        "running": parse_status.get("running", False),
        "progress": parse_status.get("progress") or "Парсинг ещё не запускался",
        "last_run": parse_status.get("last_run") or "Никогда",
        "logs": parse_logs[-30:] if parse_logs else ["Парсинг ещё не запускался. Нажмите «Начать парсинг»."]
    }


if __name__ == "__main__":
    uvicorn.run("api:app", reload=True)