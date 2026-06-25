import psycopg2
import os

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "VKR"),
    "user": os.getenv("POSTGRES_USER", "Alexs"),
    "password": os.getenv("POSTGRES_PASSWORD", "root")
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_listings (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(50) NOT NULL,
            external_id VARCHAR(100),
            url TEXT,

            title TEXT,
            price DECIMAL(15,2),
            price_per_sqm DECIMAL(15,2),
            property_type VARCHAR(50),
            market_type VARCHAR(50),
            address_raw TEXT,

            rooms SMALLINT,
            area_total DECIMAL(8,2),
            area_kitchen DECIMAL(8,2),
            area_living DECIMAL(8,2),
            floor SMALLINT,
            floors_total SMALLINT,

            balcony_count INTEGER DEFAULT 0,
            loggia_count INTEGER DEFAULT 0,
            bathroom_separate INTEGER DEFAULT 0,
            bathroom_combined INTEGER DEFAULT 0,

            finishing VARCHAR(50),
            build_year SMALLINT,
            building_type VARCHAR(50),

            metro_station VARCHAR(200),
            metro_distance INTEGER,

            views_count INTEGER,
            published_at TIMESTAMP,
            scraped_at TIMESTAMP DEFAULT NOW(),

            latitude DECIMAL(10,8),
            longitude DECIMAL(11,8),

            UNIQUE(source, external_id)
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("Таблицы успешно созданы!")


def create_missing_tables():
    """Создаёт недостающие таблицы."""
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица уникальных объектов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unified_objects (
            id SERIAL PRIMARY KEY,
            geohash VARCHAR(12),
            canonical_address TEXT,
            latitude DECIMAL(10,8),
            longitude DECIMAL(11,8),

            property_type VARCHAR(50),
            rooms SMALLINT,
            area_total DECIMAL(8,2),
            area_kitchen DECIMAL(8,2),
            area_living DECIMAL(8,2),
            floor SMALLINT,
            floors_total SMALLINT,

            building_year SMALLINT,
            building_type VARCHAR(50),

            metro_station VARCHAR(200),
            metro_distance INTEGER,

            last_price DECIMAL(15,2),
            last_price_per_sqm DECIMAL(15,2),
            last_seen_at TIMESTAMP,
            first_seen_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),

            status VARCHAR(20) DEFAULT 'active'
        );
    """)

    # Таблица связей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS object_matches (
            id SERIAL PRIMARY KEY,
            raw_listing_id BIGINT NOT NULL REFERENCES raw_listings(id) ON DELETE CASCADE,
            unified_object_id BIGINT NOT NULL REFERENCES unified_objects(id) ON DELETE CASCADE,
            confidence_score DECIMAL(3,2) DEFAULT 1.00,
            matched_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(raw_listing_id, unified_object_id)
        );
    """)

    # Таблица истории цен
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
            unified_object_id BIGINT NOT NULL REFERENCES unified_objects(id) ON DELETE CASCADE,
            source VARCHAR(50),
            price DECIMAL(15,2),
            price_per_sqm DECIMAL(15,2),
            date DATE NOT NULL DEFAULT CURRENT_DATE,

            UNIQUE(unified_object_id, source, date)
        );
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Недостающие таблицы созданы!")

def save_to_db(data: dict, url: str, external_id: str, source: str = "cian"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO raw_listings (
            source, external_id, url,
            title, price, price_per_sqm, property_type, market_type, address_raw,
            rooms, area_total, area_kitchen, area_living,
            floor, floors_total,
            balcony_count, loggia_count,
            bathroom_separate, bathroom_combined,
            finishing, build_year, building_type,
            metro_station, metro_distance,
            views_count, published_at, scraped_at,
            latitude, longitude
        ) VALUES (
            %(source)s, %(external_id)s, %(url)s,
            %(title)s, %(price)s, %(price_per_sqm)s, %(property_type)s, %(market_type)s, %(address)s,
            %(rooms)s, %(area_total)s, %(area_kitchen)s, %(area_living)s,
            %(floor)s, %(floors_total)s,
            %(balcony)s, %(loggia)s,
            %(bathroom_sep)s, %(bathroom_com)s,
            %(finishing)s, %(build_year)s, %(building_type)s,
            %(metro_station)s, %(metro_distance)s,
            %(views)s, %(published)s, NOW(),
            %(latitude)s, %(longitude)s
        )
        ON CONFLICT (source, external_id) DO UPDATE SET
            price = EXCLUDED.price,
            price_per_sqm = EXCLUDED.price_per_sqm,
            scraped_at = NOW()
    """, {
        "source": source,
        "external_id": external_id,
        "url": url,
        "title": data.get('Название'),
        "price": int(data.get('Стоимость', 0)) if data.get('Стоимость') else None,
        "price_per_sqm": int(data.get('Стоимость за метр', 0)),
        "property_type": data.get('Тип жилья'),
        "market_type": data.get('Тип рынка'),
        "address": data.get('Адрес'),
        "rooms": data.get('Количество комнат') if data.get('Количество комнат') != "-" else None,
        "area_total": data.get('Общая площадь(м²)') if data.get('Общая площадь(м²)') != "-" else None,
        "area_kitchen": data.get('Площадь кухни(м²)') if data.get('Площадь кухни(м²)') != "-" else None,
        "area_living": data.get('Жилая площадь(м²)') if data.get('Жилая площадь(м²)') != "-" else None,
        "floor": data.get('Этаж'),
        "floors_total": data.get('Всего этажей'),
        "balcony": data.get('Балкон', 0),
        "loggia": data.get('Лоджия', 0),
        "bathroom_sep": data.get('Санузел(Раздельный)') if data.get('Санузел(Раздельный)') != "-" else 0,
        "bathroom_com": data.get('Санузел(Совмещенный)') if data.get('Санузел(Совмещенный)') != "-" else 0,
        "finishing": data.get('Ремонт') if data.get('Ремонт') != "-" else None,
        "build_year": int(data.get('Год постройки')) if data.get('Год постройки') and data.get('Год постройки') != "-" else None,
        "building_type": data.get('Тип дома'),
        "metro_station": data.get('Название метро'),
        "metro_distance": data.get('Путь до метро(мин)'),
        "views": int(data.get('Просмотрено', "0")),
        "published": data.get('Дата обновления') if data.get('Дата обновления') != "Не указано" else None,
        "latitude": data.get('Широта'),
        "longitude": data.get('Долгота')
    })

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Сохранено: {data.get('title_name', '')[:60]}...")

if __name__ == "__main__":
    create_tables()
    create_missing_tables()