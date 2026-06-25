import asyncio
import re
import time
import sys
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright
from pyarrow.lib import null

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import save_to_db


async def get_coordinates_from_script(page, current_object_id: str):
    """Извлекает координаты текущего объекта из JavaScript на странице."""
    try:
        # Ищем скрипт, содержащий alike_objects
        scripts = await page.query_selector_all('script')
        for script in scripts:
            text = await script.inner_text()
            if 'alike_objects' in text and 'latitude' in text and current_object_id in text:
                # Извлекаем latitude и longitude для текущего объекта
                lat_match = re.search(rf'"{current_object_id}".*?"latitude":"([\d.]+)"', text, re.DOTALL)
                lon_match = re.search(rf'"{current_object_id}".*?"longitude":"([\d.]+)"', text, re.DOTALL)

                if lat_match and lon_match:
                    lat = float(lat_match.group(1))
                    lon = float(lon_match.group(1))
                    return lat, lon
        return None, None
    except Exception as e:
        print(f"Ошибка извлечения координат: {e}")
        return None, None

async def get_coords_evaluate(page, current_object_id: str):
    """Извлекает координаты через выполнение JS."""
    try:
        coords = await page.evaluate(f"""
            () => {{
                if (window.alike_objects && window.alike_objects['{current_object_id}']) {{
                    var obj = window.alike_objects['{current_object_id}'];
                    return {{
                        lat: parseFloat(obj.latitude),
                        lon: parseFloat(obj.longitude)
                    }};
                }}
                return null;
            }}
        """)
        if coords:
            return coords['lat'], coords['lon']
        return None, None
    except:
        return None, None

def parse_bathroom(value: str):
    """
    Парсит значение поля 'Санузел'.
    Возвращает (separate, combined) — количество раздельных и совмещённых.

    'Раздельный'        → (1, 0)
    'Совмещённый'       → (0, 1)
    '2 с/у'             → (2, 0)
    '3 с/у'             → (3, 0)
    'Два раздельных'    → (2, 0)
    'Совмещённый, Раздельный' → (1, 1)
    '-'                 → (0, 0)
    """
    if not value or value == '-' or value == 'Нет':
        return 0, 0

    value_lower = value.lower().strip()
    separate = 0
    combined = 0

    # Случай: "2 с/у" или "3 с/у"
    match = re.search(r'(\d+)\s*с/у', value_lower)
    if match:
        separate = int(match.group(1))
        return separate, combined

    # Случай: "Два раздельных", "Три раздельных"
    numbers = {
        'один': 1, 'одна': 1, 'одно': 1,
        'два': 2, 'две': 2,
        'три': 3, 'четыре': 4, 'пять': 5
    }

    for word, num in numbers.items():
        if word in value_lower:
            if 'раздель' in value_lower:
                separate = num
            elif 'совмещ' in value_lower:
                combined = num
            return separate, combined

    # Базовые случаи
    if 'раздель' in value_lower:
        separate = 1
    if 'совмещ' in value_lower:
        combined = 1

    return separate, combined

def parse_balcony_loggia(value: str):
    """
    Парсит значение поля 'Балкон' из ИНКОМ.
    Возвращает (balcony, loggia) — оба 0 или 1.

    'Балкон'      → (1, 0)
    'Лоджия'      → (0, 1)
    'Нет'         → (0, 0)
    'Балкон, Лоджия' → (1, 1)
    '-'           → (0, 0)
    """
    if not value or value == '-' or value == 'Нет':
        return 0, 0

    value_lower = value.lower()
    balcony = 1 if 'балкон' in value_lower else 0
    loggia = 1 if 'лоджи' in value_lower else 0

    return balcony, loggia


async def get_all_params(page):
    """Извлекает все параметры из блока .information__row"""
    params = {}

    rows = await page.query_selector_all('.information__row')
    for row in rows:
        try:
            # Ключ (левый столбец)
            key_elem = await row.query_selector('.information__column:first-child span')
            # Значение (правый столбец)
            val_elem = await row.query_selector('.information__column:last-child span')

            if key_elem and val_elem:
                key = (await key_elem.inner_text()).strip()
                value = (await val_elem.inner_text()).strip()
                params[key] = value
        except:
            continue

    return params

def clean_number(value_str):
    """Извлекает число из строки."""
    if not value_str or value_str == '-' or value_str == '':
        return 0.0
    if isinstance(value_str, (int, float)):
        return float(value_str)
    cleaned = str(value_str).replace(' ', '').replace(',', '.')
    match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
    if match:
        try:
            return float(match.group(1))
        except:
            return 0.0
    return 0.0

async def run_parser(pages: int = 1) -> int:
    all_links = []
    success = 0
    start_time = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-infobars',
                '--disable-setuid-sandbox',
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            permissions=["geolocation"],
            geolocation={"latitude": 55.7558, "longitude": 37.6173},
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
        )

        page = await context.new_page()

        # Маскировка WebDriver
        await page.add_init_script("""
            // Убираем webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // Подменяем plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Подменяем languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ru-RU', 'ru', 'en-US', 'en']
            });

            // Подменяем platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });

            // Chrome runtime
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)

        # ---------- ШАГ 1: Сбор ссылок ----------
        print(f"🔍 Сбор ссылок с {pages} страниц...")
        for page_num in range(1, pages + 1):
            url = f"https://www.incom.ru/kupit-kvartiru/page-{page_num}/"
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)

            cards = await page.query_selector_all('.catalog-f__item.c-i')
            for card in cards:
                try:
                    # Ссылка и заголовок — это один элемент <a class="about__title">
                    link_elem = await card.query_selector('a.about__title')
                    link_url = await link_elem.get_attribute('href') if link_elem else None
                    title = await link_elem.inner_text() if link_elem else "Без названия"

                    if link_url:
                        # Добавляем домен, если ссылка относительная
                        if link_url.startswith('/'):
                            link_url = f"https://www.incom.ru{link_url}"
                        all_links.append({'title': title.strip(), 'url': link_url, 'page': page_num})
                        print(f"  [{len(all_links)}] {title.strip()[:60]}...")
                except:
                    continue

        print(f"\n✅ Собрано {len(all_links)} ссылок")
        # ---------- ШАГ 2: Парсинг каждой ссылки ----------
        print(f"\n📊 Парсинг объявлений...")
        for idx, link_info in enumerate(all_links, 1):
            print(f"\n[{idx}/{len(all_links)}] {link_info['title'][:60]}...")

            try:
                await page.goto(link_info['url'], wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(1.5, 2.5))

                # Заголовок
                title_elem = await page.query_selector('h1')
                title_name = await title_elem.inner_text() if title_elem else link_info['title']

                # Цена
                price = 0
                price_elem = await page.query_selector('.price__title')
                if price_elem:
                    price = int(clean_number(await price_elem.inner_text()))

                # Цена за метр
                price_per_sqm = 0
                ppm_elem = await page.query_selector('.price__subtitle')
                if ppm_elem:
                    price_per_sqm = int(clean_number(await ppm_elem.inner_text()))

                # Адрес и метро
                address = 'Не указан'
                metro_station = '-'
                metro_minutes = 0

                addr_elem = await page.query_selector('.location-info')
                if addr_elem:
                    lines = (await addr_elem.inner_text()).strip().split('\n')
                    lines = [l.strip() for l in lines if l.strip()]

                    if lines:
                        address = lines[0]

                    for i, line in enumerate(lines):
                        if 'мин' in line.lower() and i > 0:
                            metro_station = lines[i - 1]
                            metro_minutes = int(clean_number(line))
                            break

                # Параметры из prop__row (комнаты, площадь, этаж)
                rooms = '-'
                total_area = 0.0
                living_area = 0.0
                kitchen_area = 0.0
                current_floor = '-'
                total_floors = '-'

                prop_rows = await page.query_selector_all('.prop__item')
                for prop in prop_rows:
                    title_elem = await prop.query_selector('.prop__title')
                    value_elem = await prop.query_selector('.prop__value')
                    if not title_elem or not value_elem:
                        continue
                    title = (await title_elem.inner_text()).strip()
                    value = (await value_elem.inner_text()).strip()

                    if title == 'Комнат':
                        rooms = value
                    elif title == 'Общая':
                        total_area = clean_number(value)
                    elif title == 'Жилая':
                        living_area = clean_number(value)
                    elif title == 'Кухня':
                        kitchen_area = clean_number(value)
                    elif title == 'Этаж':
                        if '/' in value:
                            parts = value.split('/')
                            current_floor = parts[0].strip()
                            total_floors = parts[1].strip()

                # Параметры из information__row (ремонт, балкон, санузел, тип дома, год постройки)
                params = await get_all_params(page)

                # Балкон и лоджия
                balcony_val = params.get('Балкон', '-')
                balcony, loggia = parse_balcony_loggia(balcony_val)

                # Санузел
                bathroom_val = params.get('Санузел', '-')
                sanusel_sep, sanusel_com = parse_bathroom(bathroom_val)

                # Ремонт
                repair = params.get('Ремонт', '-')

                # Тип дома
                type_house = params.get('Тип дома', '-')

                # Год постройки
                build_year = params.get('Год постройки', '-')
                if build_year == '-':
                    build_year = None

                # Тип жилья и рынок
                object_type = params.get('Объект', '')
                property_type = 'Апартаменты' if 'апартамент' in object_type.lower() else 'Квартира'
                market_type = params.get('Тип', 'Вторичка')

                # Координаты
                current_object_id = link_info['url'].rstrip('/').split('/')[-1]
                lat, lon = await get_coordinates_from_script(page, current_object_id)
                if lat is None:
                    lat, lon = await get_coords_evaluate(page, current_object_id)

                # Если цена за метр не найдена — считаем
                if price_per_sqm == 0 and total_area > 0 and price > 0:
                    price_per_sqm = int(price / total_area)

                # Формируем строку для БД
                row = {
                    'Название': title_name,
                    'Стоимость': price,
                    'Стоимость за метр': price_per_sqm,
                    'Тип жилья': property_type,
                    'Тип рынка': market_type,
                    'Адрес': address,
                    'Количество комнат': rooms,
                    'Общая площадь(м²)': total_area,
                    'Площадь кухни(м²)': kitchen_area,
                    'Жилая площадь(м²)': living_area,
                    'Этаж': current_floor,
                    'Всего этажей': total_floors,
                    'Балкон': balcony,
                    'Лоджия': loggia,
                    'Санузел(Раздельный)': sanusel_sep,
                    'Санузел(Совмещенный)': sanusel_com,
                    'Ремонт': repair,
                    'Дата обновления': None,
                    'Просмотрено': 0,
                    'Год постройки': build_year,
                    'Тип дома': type_house,
                    'Название метро': metro_station,
                    'Путь до метро(мин)': metro_minutes,
                    'Долгота': lon,
                    'Широта': lat
                }

                # Сохранение в БД
                external_id = f"INCOM_{link_info['url'].rstrip('/').split('/')[-1]}"
                save_to_db(data=row, url=link_info['url'], external_id=external_id, source="incom")

                success += 1
                print(f"  ✅ {title_name[:50]}... | {price} ₽ | {total_area} м² | {metro_station}")

            except Exception as e:
                print(f"  ❌ Ошибка: {type(e).__name__}")
                continue

            await asyncio.sleep(random.uniform(0.5, 1.5))
        await browser.close()

    end_time = time.time()
    print(f"\n{'='*60}")
    print(f"⏱️  Общее время: {int((end_time-start_time)//60)} мин {int((end_time-start_time)%60)} сек")
    print(f"✅ ИТОГО: собрано {success} из {len(all_links)} объявлений")
    return success

if __name__ == "__main__":
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    asyncio.run(run_parser(pages))