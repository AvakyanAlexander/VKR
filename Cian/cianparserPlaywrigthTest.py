import asyncio
import json
import re
import time
import sys
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import save_to_db


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def clean_number(value_str):
    if not value_str or value_str == '-':
        return 0.0
    cleaned = value_str.replace(' ', '').replace(',', '.')
    match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
    if match:
        try:
            return float(match.group(1))
        except:
            return 0.0
    return 0.0


async def get_all_offer_data(page):
    """Извлекает все данные об объявлении из window._cianConfig через Playwright."""
    try:
        data = await page.evaluate("""
            () => {
                try {
                    var configs = window._cianConfig['frontend-offer-card'];
                    if (configs && configs.length > 0) {
                        for (var i = 0; i < configs.length; i++) {
                            if (configs[i].key === 'defaultState' && configs[i].value) {
                                return configs[i].value;
                            }
                        }
                    }
                    return null;
                } catch(e) {
                    return null;
                }
            }
        """)

        if not data:
            return None

        if 'offerData' not in data or 'offer' not in data['offerData']:
            return None

        offer = data['offerData']['offer']

        title_name = offer.get('title', 'Не указано')

        price = None
        if 'bargainTerms' in offer:
            price = offer['bargainTerms'].get('price')

        total_area = offer.get('totalArea')
        living_area = offer.get('livingArea')
        kitchen_area = offer.get('kitchenArea')

        rooms_count = offer.get('roomsCount')
        if rooms_count is None:
            title_lower = title_name.lower()
            if 'студия' in title_lower:
                rooms_count = 0
            else:
                match = re.search(r'(\d+)[-\s]*комн', title_lower)
                if match:
                    rooms_count = int(match.group(1))
                else:
                    rooms_count = '-'

        floor = offer.get('floorNumber')
        all_floor = offer.get('building', {}).get('floorsCount')

        is_apartments = offer.get('isApartments', False)
        type_room = "Апартаменты" if is_apartments else "Квартира"

        category = offer.get('category', '')
        if 'newBuilding' in category:
            market_type = "Новостройка"
        elif 'flatSale' in category or 'apartmentsSale' in category:
            market_type = "Вторичка"
        else:
            nb = offer.get('newbuilding')
            if nb and isinstance(nb, dict) and nb.get('id'):
                market_type = "Новостройка"
            elif offer.get('isFromBuilder') or offer.get('isFromDeveloper'):
                market_type = "Новостройка"
            else:
                market_type = "Вторичка"

        building = offer.get('building', {})
        material_type = building.get('materialType', '')
        material_map = {
            'monolith': 'монолитный', 'brick': 'кирпичный', 'panel': 'панельный',
            'block': 'блочный', 'wood': 'деревянный',
            'Monolithbrick': 'монолитно-кирпичный', 'monolithbrick': 'монолитно-кирпичный',
            'monolith_brick': 'монолитно-кирпичный', 'monolitbrick': 'монолитно-кирпичный',
            'brick-monolith': 'монолитно-кирпичный', 'brick_monolith': 'монолитно-кирпичный',
            'foam': 'пеноблочный', 'stalin': 'сталинский', 'stalinka': 'сталинский',
            'khrushchev': 'хрущёвка', 'brezhnev': 'брежневка', 'modern': 'современный'
        }
        type_house = material_map.get(material_type, material_map.get(material_type.lower()))
        if not type_house:
            type_house = material_type.capitalize() if material_type else '-'

        build_year = offer.get('building', {}).get('buildYear') or '-'

        edit_date = offer.get('editDate')
        if edit_date:
            try:
                dt = datetime.fromisoformat(edit_date.replace('+00:00', ''))
                date = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                date = edit_date
        else:
            date = 'Не указано'

        stats = offer.get('stats', {})
        views = stats.get('totalViewsFormattedString', '0 просмотров')

        address_parts = []
        if 'geo' in offer and 'address' in offer['geo']:
            for addr in offer['geo']['address']:
                short_name = addr.get('shortName', addr.get('name', ''))
                if short_name:
                    address_parts.append(short_name)
            address = ", ".join(address_parts)
        else:
            address = 'Не указан'

        lat = lon = None
        if 'geo' in offer and 'coordinates' in offer['geo']:
            coords = offer['geo']['coordinates']
            lat = coords.get('lat')
            lon = coords.get('lng')

        nearest = {'station': 'Не указано', 'minutes': None}
        if 'geo' in offer and 'undergrounds' in offer['geo'] and offer['geo']['undergrounds']:
            first_metro = offer['geo']['undergrounds'][0]
            nearest = {
                'station': first_metro.get('name', 'Не указано'),
                'minutes': first_metro.get('travelTime', None)
            }

        balcony_count = offer.get('balconiesCount', 0)
        loggia_count = offer.get('loggiasCount', 0)

        separate_wc = offer.get('separateWcsCount', 0)
        combined_wc = offer.get('combinedWcsCount', 0)
        sanusel_sep = "-" if separate_wc == 0 else separate_wc
        sanusel_com = "-" if combined_wc == 0 else combined_wc

        repair_type = offer.get('repairType', '')
        repair_map = {
            'design': 'Дизайнерский', 'fine': 'Хороший', 'rough': 'Черновая',
            'preFine': 'Предчистовая', 'euro': 'Евроремонт', 'cosmetic': 'Косметический',
            'No': '-', 'no': '-'
        }
        renovation = repair_map.get(repair_type, repair_type.capitalize() if repair_type else '-')

        return {
            'title_name': title_name,
            'price': price,
            'category': market_type,
            'floor': floor,
            'all_floor': all_floor,
            'build_year': build_year,
            'type_room': type_room,
            'count_room': rooms_count,
            'total_area': total_area,
            'living_area': living_area,
            'kitchen_area': kitchen_area,
            'balcony': balcony_count,
            'loggia': loggia_count,
            'sanusel_sep': sanusel_sep,
            'sanusel_com': sanusel_com,
            'renovation': renovation,
            'date': date,
            'viewed': views,
            'type_house': type_house,
            'nearest': nearest,
            'address': address,
            'lat': lat,
            'lon': lon
        }
    except Exception as e:
        print(f"Ошибка при извлечении данных: {e}")
        return None


# ============================================================
# ОСНОВНАЯ АСИНХРОННАЯ ФУНКЦИЯ ПАРСИНГА
# ============================================================

async def run_parser(pages: int = 1) -> int:
    all_links = []
    all_data = []
    start_time = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1920,1080'
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # ---------- ШАГ 1: Сбор ссылок ----------
        print(f"Сбор ссылок с {pages} страниц...")
        for page_num in range(1, pages + 1):
            url = f"https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&p={page_num}&region=1"
            await page.goto(url, wait_until="commit", timeout=15000)
            await asyncio.sleep(random.uniform(0.8, 1.2))

            cards = await page.query_selector_all('[data-testid="offer-card"]')
            for card in cards:
                try:
                    link_elem = await card.query_selector('[data-name="LinkArea"] a')
                    link_url = await link_elem.get_attribute('href')
                    title_elem = await card.query_selector('[data-mark="OfferTitle"] span')
                    title = await title_elem.inner_text() if title_elem else "Без названия"
                    all_links.append({'title': title, 'url': link_url, 'page': page_num})
                    print(f"[{len(all_links)}] {title[:60]}...")
                except:
                    continue

            await asyncio.sleep(random.uniform(0.8, 1.2))

        print(f"\nСобрано {len(all_links)} ссылок")

        # ---------- ШАГ 2: Парсинг каждой ссылки ----------
        print(f"\nПарсинг объявлений...")
        success = 0

        for idx, link_info in enumerate(all_links, 1):
            print(f"\n[{idx}/{len(all_links)}] {link_info['url'][:80]}...")

            try:
                # Ждём только HTML, не ждём картинки и стили
                await page.goto(link_info['url'], wait_until="commit", timeout=15000)
                # Минимальная пауза для выполнения JS
                await asyncio.sleep(random.uniform(0.3, 0.6))

                data = await get_all_offer_data(page)
                if not data:
                    print("Данные не извлечены")
                    continue

                if data['title_name'] == "Не указано":
                    try:
                        title_elem = await page.query_selector('[data-name="OfferTitleNew"] h1')
                        if title_elem:
                            data['title_name'] = await title_elem.inner_text()
                    except:
                        pass

                row = {
                    'Название': data['title_name'],
                    'Стоимость': int(data['price']),
                    'Стоимость за метр': int(data['price'] / clean_number(data['total_area'])),
                    'Тип жилья': data['type_room'],
                    'Тип рынка': data['category'],
                    'Адрес': data['address'],
                    'Количество комнат': data['count_room'],
                    'Общая площадь(м²)': clean_number(data['total_area']),
                    'Площадь кухни(м²)': clean_number(data['kitchen_area']),
                    'Жилая площадь(м²)': clean_number(data['living_area']),
                    'Этаж': data['floor'],
                    'Всего этажей': data['all_floor'],
                    'Балкон': data['balcony'],
                    'Лоджия': data['loggia'],
                    'Санузел(Раздельный)': data['sanusel_sep'],
                    'Санузел(Совмещенный)': data['sanusel_com'],
                    'Ремонт': data['renovation'],
                    'Дата обновления': data['date'],
                    'Просмотрено': data['viewed'].split()[0] if data['viewed'] else 0,
                    'Год постройки': data['build_year'],
                    'Тип дома': data['type_house'],
                    'Название метро': data['nearest']['station'],
                    'Путь до метро(мин)': data['nearest']['minutes'],
                    'Долгота': data['lon'],
                    'Широта': data['lat']
                }

                external_id = link_info['url'].split('/')[-2]
                save_to_db(data=row, url=link_info['url'], external_id=external_id, source="cian")

                all_data.append(row)
                success += 1
                print(f"{data['title_name'][:50]}... | {data['price']} ₽")

            except Exception as e:
                print(f"Ошибка: {type(e).__name__}")
                continue

            await asyncio.sleep(random.uniform(0.5, 1.0))

        await browser.close()

    end_time = time.time()
    total_time = end_time - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    avg_time = total_time / success if success > 0 else 0

    print(f"\n{'='*60}")
    print(f"Общее время сбора: {minutes} мин {seconds} сек")
    print(f"Среднее время на одно объявление: {avg_time:.2f} сек")
    print(f"ИТОГО: собрано {success} из {len(all_links)} объявлений")
    return success


# ============================================================
# ТОЧКА ВХОДА
# ============================================================
if __name__ == "__main__":
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"Запуск парсера Циан с {pages} стр.")
    count = asyncio.run(run_parser(pages))
    print(f"Готово! Собрано {count} объявлений.")