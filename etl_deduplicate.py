import psycopg2
import geohash2
from difflib import SequenceMatcher

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "VKR",
    "user": "Alexs",
    "password": "root"
}

THRESHOLD = 0.75  # Порог для объединения


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def calculate_match_score(r, u):
    """Гибридный scoring между сырой записью (r) и унифицированным объектом (u)."""
    score = 0.0

    # 1. Геохеш (30%) — уже совпал, иначе бы не попали в сравнение
    score += 0.30

    # 2. Площадь общая ±1 м² (25%)
    if r["area_total"] and u["area_total"]:
        diff = abs(r["area_total"] - u["area_total"])
        if diff <= 1.0:
            score += 0.25
        elif diff <= 3.0:
            score += 0.15

    # 3. Этаж (20%)
    if r["floor"] and u["floor"]:
        if r["floor"] == u["floor"]:
            score += 0.20

    # 4. Количество комнат (15%)
    if r["rooms"] and u["rooms"]:
        if r["rooms"] == u["rooms"]:
            score += 0.15

    # 5. Похожесть адреса (10%)
    if r["address_raw"] and u["canonical_address"]:
        similarity = SequenceMatcher(None, r["address_raw"], u["canonical_address"]).ratio()
        score += similarity * 0.10

    return score


def run_deduplication():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Находим все сырые записи, ещё не привязанные к объектам
    cursor.execute("""
        SELECT r.id, r.latitude, r.longitude, r.area_total, r.floor, 
               r.rooms, r.address_raw, r.price, r.price_per_sqm, r.source,
               r.property_type, r.market_type, r.area_kitchen, r.area_living,
               r.floors_total, r.building_type, r.build_year,
               r.metro_station, r.metro_distance, r.title
        FROM raw_listings r
        LEFT JOIN object_matches m ON r.id = m.raw_listing_id
        WHERE m.raw_listing_id IS NULL
          AND r.latitude IS NOT NULL
          AND r.longitude IS NOT NULL
    """)

    unmatched = cursor.fetchall()
    print(f"Найдено {len(unmatched)} непривязанных записей")

    for row in unmatched:
        raw_id = row[0]
        lat = float(row[1])
        lon = float(row[2])

        gh = geohash2.encode(lat, lon, precision=7)

        cursor.execute("""
            SELECT id, geohash, canonical_address, latitude, longitude,
                   area_total, floor, rooms
            FROM unified_objects
            WHERE geohash = %s
        """, (gh,))

        candidates = cursor.fetchall()

        best_score = 0.0
        best_match_id = None

        for candidate in candidates:
            r_dict = {
                "area_total": row[3],
                "floor": row[4],
                "rooms": row[5],
                "address_raw": row[6]
            }
            u_dict = {
                "area_total": candidate[5],
                "floor": candidate[6],
                "rooms": candidate[7],
                "canonical_address": candidate[2]
            }

            score = calculate_match_score(r_dict, u_dict)

            if score > best_score:
                best_score = score
                best_match_id = candidate[0]

        if best_score >= THRESHOLD and best_match_id:
            unified_id = best_match_id
            cursor.execute("""
                INSERT INTO object_matches (raw_listing_id, unified_object_id, confidence_score)
                VALUES (%s, %s, %s)
                ON CONFLICT (raw_listing_id, unified_object_id) DO NOTHING
            """, (raw_id, unified_id, round(best_score, 2)))
        else:
            # Создаём новый объект со ВСЕМИ полями
            cursor.execute("""
                INSERT INTO unified_objects (
                    geohash, canonical_address, latitude, longitude,
                    area_total, area_kitchen, area_living,
                    floor, floors_total, rooms,
                    building_type, building_year,
                    property_type, metro_station, metro_distance
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                gh, row[6], lat, lon,
                row[3], row[12], row[13],   # area_total, area_kitchen, area_living
                row[4], row[14], row[5],    # floor, floors_total, rooms
                row[15], row[16],           # building_type, build_year
                row[10], row[17], row[18]   # property_type, metro_station, metro_distance
            ))

            unified_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO object_matches (raw_listing_id, unified_object_id, confidence_score)
                VALUES (%s, %s, 1.00)
            """, (raw_id, unified_id))

        # Обновляем last_price, last_seen_at и ВСЕ доп. поля
        cursor.execute("""
            UPDATE unified_objects
            SET last_price = %s,
                last_price_per_sqm = %s,
                property_type = COALESCE(property_type, %s),
                building_type = COALESCE(building_type, %s),
                building_year = COALESCE(building_year, %s),
                metro_station = COALESCE(metro_station, %s),
                metro_distance = COALESCE(metro_distance, %s),
                area_kitchen = COALESCE(area_kitchen, %s),
                area_living = COALESCE(area_living, %s),
                floors_total = COALESCE(floors_total, %s),
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
        """, (
            row[7], row[8],           # price, price_per_sqm
            row[10],                  # property_type
            row[15],                  # building_type
            row[16],                  # build_year
            row[17],                  # metro_station
            row[18],                  # metro_distance
            row[12],                  # area_kitchen
            row[13],                  # area_living
            row[14],                  # floors_total
            unified_id
        ))

        cursor.execute("""
            INSERT INTO price_history (unified_object_id, source, price, price_per_sqm, date)
            VALUES (%s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT (unified_object_id, source, date) DO UPDATE SET
                price = EXCLUDED.price,
                price_per_sqm = EXCLUDED.price_per_sqm
        """, (unified_id, row[9], row[7], row[8]))

        print(f"  Запись {raw_id}: score={best_score:.2f} → unified_id={unified_id}")

    conn.commit()
    cursor.close()
    conn.close()
    print("Дедупликация завершена!")


if __name__ == "__main__":
    run_deduplication()