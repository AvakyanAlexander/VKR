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

CREATE TABLE IF NOT EXISTS unified_objects (
    id BIGSERIAL PRIMARY KEY,
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
    building_type VARCHAR(50),
    build_year SMALLINT,
    metro_station VARCHAR(200),
    metro_distance INTEGER,
    last_price DECIMAL(15,2),
    last_price_per_sqm DECIMAL(15,2),
    last_seen_at TIMESTAMP,
    first_seen_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS object_matches (
    id BIGSERIAL PRIMARY KEY,
    raw_listing_id BIGINT NOT NULL REFERENCES raw_listings(id) ON DELETE CASCADE,
    unified_object_id BIGINT NOT NULL REFERENCES unified_objects(id) ON DELETE CASCADE,
    confidence_score DECIMAL(3,2),
    matched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(raw_listing_id, unified_object_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    unified_object_id BIGINT NOT NULL REFERENCES unified_objects(id) ON DELETE CASCADE,
    source VARCHAR(50),
    price DECIMAL(15,2),
    price_per_sqm DECIMAL(15,2),
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE(unified_object_id, source, date)
);