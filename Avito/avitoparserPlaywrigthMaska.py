import asyncio
import json
import re
import time
import sys
import os
import random
import dateparser
from datetime import datetime
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import save_to_db


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (ВОССТАНОВЛЕНЫ ИЗ ОРИГИНАЛА)
# ============================================================

def clean_number(value_str):
    """Преобразует строку в число."""
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


def extract_external_id_avito(url: str) -> str:
    """Извлекает ID объявления из URL Авито.
    Пример: '..._8059923876' → '8059923876'
    """
    match = re.search(r'_(\d{8,})(?:\?|$)', url)
    if match:
        return match.group(1)
    return url.rstrip('/').split('/')[-1].split('?')[0]


def parse_balcony_loggia(value):
    """Определяет наличие балкона и лоджии.
    Возвращает: (балкон, лоджия) — 1 или 0.
    """
    if not value or value == '-':
        return 0, 0
    value_lower = value.lower().strip()
    balcony = 1 if 'балкон' in value_lower else 0
    loggia = 1 if 'лоджия' in value_lower else 0
    return balcony, loggia


def parse_bathroom(bathroom_value):
    """Определяет тип санузла.
    Возвращает: (раздельный, совмещенный) — 1 или 0.
    """
    if not bathroom_value or bathroom_value == '-':
        return 0, 0
    bathroom_lower = bathroom_value.lower().strip()
    if 'раздельн' in bathroom_lower:
        return 1, 0
    elif 'совмещен' in bathroom_lower:
        return 0, 1
    return 0, 0


def get_apartment_type(title):
    """Определяет тип жилья по названию объявления."""
    if not title:
        return 'Не определено'
    title_lower = title.lower()
    if 'апартамент' in title_lower:
        return 'Апартаменты'
    elif 'квартир' in title_lower or 'к.' in title_lower.split()[0]:
        return 'Квартира'
    return 'Не определено'


async def get_metro_fast(page):
    """Парсинг первого метро с Авито (Playwright)."""
    try:
        # Ищем все блоки с информацией о метро
        metro_blocks = await page.query_selector_all('span._22d8cf68e753a9b9')

        if metro_blocks:
            # Берём первый блок (первое метро)
            first_block = metro_blocks[0]

            # Название станции — внутри span без класса (второй span)
            station_spans = await first_block.query_selector_all('span')
            station_text = '-'
            for s in station_spans:
                text = (await s.inner_text()).strip()
                # Название станции — это текст без "мин" и без иконки
                if text and 'мин' not in text and len(text) > 1:
                    station_text = text
                    break

            # Время — в span с классом _975960bc91729d0a
            time_span = await first_block.query_selector('span._975960bc91729d0a')
            time_text = await time_span.inner_text() if time_span else '-'
            # Оставляем только первое число ("11" из "11–15 мин.")
            minutes = clean_number(time_text) if time_text != '-' else 0

            return station_text, int(minutes) if minutes else 0
    except:
        pass

    return '-', 0


async def get_coordinates(page):
    """Получает координаты из data-атрибутов карты (Playwright-версия)."""
    try:
        map_wrapper = await page.query_selector('[data-marker="item-map-wrapper"]')
        if map_wrapper:
            lat = await map_wrapper.get_attribute('data-map-lat')
            lon = await map_wrapper.get_attribute('data-map-lon')
            return float(lat) if lat else None, float(lon) if lon else None
    except:
        pass
    return None, None


def parse_russian_date(date_str):
    """Преобразует русскую дату в datetime."""
    if not date_str or date_str == '-':
        return None
    result = dateparser.parse(date_str, languages=['ru'])
    return result


async def get_property_type(page):
    """Определяет тип жилья: Вторичка или Новостройка (Playwright-версия)."""
    try:
        breadcrumbs = await page.query_selector_all(
            '[data-marker="breadcrumbs"] a, #bx_item-breadcrumbs a'
        )
        for crumb in breadcrumbs:
            text = (await crumb.inner_text()).strip()
            if text in ('Вторичка', 'Вторички'):
                return 'Вторичка'
            elif text in ('Новостройка', 'Новостройки'):
                return 'Новостройка'
    except:
        pass
    return 'Не определено'


async def get_all_params(page):
    """Собирает параметры из ВСЕХ блоков bx_item-params (Playwright-версия)."""
    params = {}
    try:
        params_blocks = await page.query_selector_all('#bx_item-params')
        for block in params_blocks:
            items = await block.query_selector_all('li')
            for item in items:
                text = (await item.inner_text()).strip()
                if ':' in text:
                    key, value = text.split(':', 1)
                    params[key.strip()] = value.strip()
    except:
        pass
    return params


# ============================================================
# ОСНОВНАЯ АСИНХРОННАЯ ФУНКЦИЯ ПАРСИНГА
# ============================================================

async def run_parser(pages: int = 1) -> int:
    all_links = []
    start_time = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1920,1080',
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        # Маскировка
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        # ---------- ШАГ 1: Сбор ссылок ----------
        print(f"🔍 Сбор ссылок с {pages} страниц...")
        for page_num in range(1, pages + 1):
            url = f"https://www.avito.ru/moskva/kvartiry/prodam-ASgBAgICAUSSA8YQ?p={page_num}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2, 3))

            cards = await page.query_selector_all('[data-marker="item"]')
            print(f"  Страница {page_num}: найдено {len(cards)} карточек")

            for card in cards:
                try:
                    link_elem = await card.query_selector('[itemprop="name"] a')
                    if not link_elem:
                        continue
                    link_url = await link_elem.get_attribute('href')
                    if link_url and link_url.startswith('/'):
                        link_url = 'https://www.avito.ru' + link_url
                    title = await link_elem.get_attribute('title')
                    if not title:
                        title = "Без названия"
                    all_links.append({'title': title, 'url': link_url, 'page': page_num})
                    print(f"  [{len(all_links)}] {title[:60]}...")
                except:
                    continue

            await asyncio.sleep(random.uniform(1.5, 2.5))

        print(f"\n✅ Собрано {len(all_links)} ссылок")

        # ---------- ШАГ 2: Парсинг каждой ссылки ----------
        print(f"\n📊 Парсинг объявлений...")
        success = 0
        errors = 0

        for idx, link_info in enumerate(all_links, 1):
            print(f"\n{'=' * 60}")
            print(f"[{idx}/{len(all_links)}] {link_info['url'][:80]}...")

            try:
                await page.goto(link_info['url'], wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(1.5, 2.5))

                # --- Основные данные ---
                title = link_info.get('title', 'Не указано')

                # Цена
                price = 0
                try:
                    price_elem = await page.query_selector('[itemprop="price"]')
                    price_str = await price_elem.get_attribute('content') if price_elem else '0'
                    price = int(price_str) if price_str and price_str.isdigit() else 0
                except:
                    pass

                # Адрес
                address = 'Не указан'
                try:
                    address_elem = await page.query_selector('[itemprop="address"] span')
                    address = await address_elem.inner_text() if address_elem else 'Не указан'
                except:
                    pass

                # Дата
                date_text = 'Не указано'
                try:
                    date_elem = await page.query_selector('[data-marker="item-view/item-date"]')
                    date_text = (await date_elem.inner_text()).replace('·', '').strip() if date_elem else 'Не указано'
                except:
                    pass

                # Просмотры
                views_count = 0
                try:
                    views_elem = await page.query_selector('[data-marker="item-view/total-views"]')
                    views_text = await views_elem.inner_text() if views_elem else '0'
                    views_count = int(clean_number(views_text))
                except:
                    pass

                # --- Параметры ---
                params = await get_all_params(page)

                # Тип рынка
                property_type = await get_property_type(page)

                # Этаж
                floor_info = params.get('Этаж', '-')
                floor_parts = floor_info.split()
                current_floor = int(clean_number(floor_parts[0])) if floor_parts else None
                total_floors = int(clean_number(floor_parts[2])) if len(floor_parts) > 2 else None

                # Санузел
                sanusel_sep, sanusel_com = parse_bathroom(params.get('Санузел', '-'))

                # Балкон/лоджия
                balcony, loggia = parse_balcony_loggia(params.get('Балкон или лоджия', '-'))

                # Метро
                station_text, time_to_metro = await get_metro_fast(page)
                metro_minutes = int(clean_number(time_to_metro)) if time_to_metro != '-' else None

                # Координаты
                lat, lon = await get_coordinates(page)

                # Площади
                total_area = clean_number(params.get('Общая площадь', '-'))
                kitchen_area = clean_number(params.get('Площадь кухни', '-'))
                living_area = clean_number(params.get('Жилая площадь', '-'))

                # Цена за метр
                price_per_meter = int(price / total_area) if price and total_area > 0 else 0

                # Формируем строку для БД
                row = {
                    'Название': title,
                    'Стоимость': int(price) if price else 0,
                    'Стоимость за метр': int(price_per_meter) if price_per_meter else 0,
                    'Тип жилья': get_apartment_type(title),
                    'Тип рынка': property_type,
                    'Адрес': address,
                    'Количество комнат': int(clean_number(params.get('Количество комнат', '0'))),
                    'Общая площадь(м²)': total_area,
                    'Площадь кухни(м²)': kitchen_area,
                    'Жилая площадь(м²)': living_area,
                    'Этаж': current_floor,
                    'Всего этажей': total_floors,
                    'Балкон': balcony,
                    'Лоджия': loggia,
                    'Санузел(Раздельный)': sanusel_sep,
                    'Санузел(Совмещенный)': sanusel_com,
                    'Ремонт': params.get('Ремонт', params.get('Отделка', '-')),
                    'Дата обновления': parse_russian_date(date_text) or datetime.now(),
                    'Просмотрено': int(views_count) if views_count else 0,
                    'Год постройки': params.get('Год постройки', '-'),
                    'Тип дома': params.get('Тип дома', '-'),
                    'Название метро': station_text,
                    'Путь до метро(мин)': metro_minutes,
                    'Долгота': float(lon) if lon else 0.0,
                    'Широта': float(lat) if lat else 0.0
                }

                # Сохранение в БД
                external_id = f"AVITO_{extract_external_id_avito(link_info['url'])}"
                save_to_db(data=row, url=link_info['url'], external_id=external_id, source="avito")

                success += 1
                print(f"  ✅ {row['Название'][:50]}... | {row['Стоимость']} ₽")
                print(f"     Площадь: {row['Общая площадь(м²)']} м² | Цена за м²: {row['Стоимость за метр']} ₽")
                print(f"     Метро: {row['Название метро']} ({row['Путь до метро(мин)']} мин)")

            except Exception as e:
                print(f"  ❌ Ошибка: {type(e).__name__}: {e}")
                errors += 1

            await asyncio.sleep(random.uniform(1.5, 3.0))

        await browser.close()

    end_time = time.time()
    total_time = end_time - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    avg_time = total_time / success if success > 0 else 0

    print(f"\n{'='*60}")
    print(f"⏱️  Общее время сбора: {minutes} мин {seconds} сек")
    print(f"⏱️  Среднее время на одно объявление: {avg_time:.2f} сек")
    print(f"✅ ИТОГО: собрано {success} из {len(all_links)} объявлений")
    print(f"❌ Ошибок: {errors}")
    return success


# ============================================================
# ТОЧКА ВХОДА
# ============================================================
if __name__ == "__main__":
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"Запуск парсера Авито с {pages} стр.")
    count = asyncio.run(run_parser(pages))
    print(f"Готово! Собрано {count} объявлений.")