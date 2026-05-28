from selenium import webdriver
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
import time
import json
import os
import pandas as pd
import dateparser
import random
import re

options = webdriver.ChromeOptions()
options.add_argument("start-maximized")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
driver = webdriver.Chrome(options=options)

stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
        )

all_data = []


def get_apartment_type(title):
    """
    Определяет тип жилья по названию объявления
    Возвращает: 'Квартира' или 'Апартаменты'
    """
    if not title:
        return 'Не определено'

    # Приводим к нижнему регистру для поиска
    title_lower = title.lower()

    # Ищем ключевые слова
    if 'апартамент' in title_lower:
        return 'Апартаменты'
    elif 'квартир' in title_lower or 'к.' in title_lower.split()[0]:
        return 'Квартира'
    else:
        return 'Не определено'

def extract_json_from_page(driver):
    """Извлекает __staticRouterHydrationData из HTML страницы"""
    try:
        html = driver.page_source

        # Ищем JSON
        match = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\)', html, re.DOTALL)

        if match:
            json_str = match.group(1)
            # Декодируем экранированные символы
            json_str = json_str.encode().decode('unicode-escape')
            data = json.loads(json_str)
            return data
        return None
    except Exception as e:
        print(f"Ошибка извлечения JSON: {e}")
        return None


def get_params_from_json(item_data):
    """Извлекает параметры из JSON"""
    params = {}

    # Параметры из paramsDto
    params_items = item_data.get('paramsDto', {}).get('items', [])
    for p in params_items:
        params[p.get('title', '')] = p.get('description', '')

    # Параметры из houseParams
    house_items = item_data.get('houseParams', {}).get('items', [])
    for p in house_items:
        params[p.get('title', '')] = p.get('description', '')

    return params


def clean_number(value_str):
    """Преобразует строку в число"""
    if not value_str or value_str == '-' or value_str == '':
        return 0.0

    if isinstance(value_str, (int, float)):
        return float(value_str)

    # Убираем пробелы и заменяем запятую на точку
    cleaned = str(value_str).replace(' ', '').replace(',', '.')

    # Извлекаем первое число
    match = re.search(r'(\d+(?:\.\d+)?)', cleaned)

    if match:
        try:
            return float(match.group(1))
        except:
            return 0.0
    return 0.0


def parse_russian_date(date_str):
    """Преобразует русскую дату в datetime"""
    if not date_str or date_str == '-':
        return None
    return dateparser.parse(date_str, languages=['ru'])


def get_metro_from_json(item_data):
    """Извлекает информацию о метро из JSON"""
    geo_refs = item_data.get('geo', {}).get('references', [])

    if geo_refs:
        first_metro = geo_refs[0]
        station = first_metro.get('content', '-')
        distance = first_metro.get('after', '-')

        # Очищаем расстояние от " км" и "–"
        distance_clean = re.sub(r'[^\d.,]', '', distance.replace('–', '.'))

        return station, clean_number(distance_clean)

    return '-', 0


def get_offers(page, city, filename='link.json'):
    """Сбор ссылок на объявления"""
    all_offers = []
    i = 1

    for page_num in range(1, page + 1):
        url = f"https://www.avito.ru/{city}/kvartiry/prodam-ASgBAgICAUSSA8YQ?p={page_num}"
        driver.get(url)
        time.sleep(random.uniform(3, 5))

        try:
            blocks = driver.find_element(By.ID, "bx_serp-item-list")
            posts = blocks.find_elements(By.CSS_SELECTOR, '[data-marker="item"]')

            for post in posts:
                title_elem = post.find_element(By.CSS_SELECTOR, '[itemprop="name"]').find_element(By.TAG_NAME, 'a')
                title = title_elem.get_attribute('title')
                title_link = title_elem.get_attribute('href')
                price = post.find_element(By.CSS_SELECTOR, '[data-marker="item-price-value"]').text

                print(f"{i}. {title} - {price}")

                offer_data = {
                    'id': i,
                    'title': title,
                    'url': title_link,
                    'price': price,
                    'page': page_num
                }
                all_offers.append(offer_data)
                i += 1

        except Exception as e:
            print(f"Ошибка при сборе ссылок: {e}")

        time.sleep(random.uniform(3, 5))

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(all_offers, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Сохранено {len(all_offers)} ссылок в файл {filename}")

    return all_offers


def get_data_from_offers():
    """Основная функция сбора данных из JSON"""
    i = 1
    errors = 0

    with open('link_test_10.json', encoding='utf-8') as f:
        all_offers = json.load(f)

    for offer in all_offers:
        print(f"\n{'=' * 60}")
        print(f"Обработка {i}/{len(all_offers)}: {offer['url']}")

        try:
            driver.get(offer['url'])
            time.sleep(random.uniform(2, 4))

            # Извлекаем JSON
            json_data = extract_json_from_page(driver)

            if not json_data:
                print("⚠️ JSON не найден")
                errors += 1
                i += 1
                continue

            # Путь к данным объявления
            try:
                item_data = json_data['loaderData']['catalog-or-main-or-item']['buyerItem']['item']
            except KeyError as e:
                print(f"❌ Неверная структура JSON: {e}")
                errors += 1
                i += 1
                continue

            # Получаем параметры
            params = get_params_from_json(item_data)

            # Информация об этаже
            floor_info = params.get('Этаж', '-')
            floor_parts = floor_info.split()
            current_floor = floor_parts[0] if floor_parts else '-'
            total_floors = floor_parts[2] if len(floor_parts) > 2 else '-'

            # Информация о санузле
            bathroom = params.get('Санузел', '').lower()
            has_separate = 'раздельный' in bathroom
            has_combined = 'совмещённый' in bathroom or 'совмещенный' in bathroom

            # Метро
            station, metro_minutes = get_metro_from_json(item_data)

            # Координаты
            coords = item_data.get('location', {}).get('coords', {})

            # Площади
            total_area = clean_number(params.get('Общая площадь', '-'))
            kitchen_area = clean_number(params.get('Площадь кухни', '-'))
            living_area = clean_number(params.get('Жилая площадь', '-'))

            # Цена
            price = item_data.get('price', 0)

            # Стоимость за метр
            price_per_meter = int(price / total_area) if price and total_area > 0 else 0

            # Просмотры
            view_stat = item_data.get('viewStat', {})
            total_views = view_stat.get('totalViews', 0)

            # Определяем тип жилья
            is_development = item_data.get('flags', {}).get('isDevelopmentSell', False)
            property_type = 'Новостройка' if is_development else 'Вторичка'
            market_type = 'Первичный' if is_development else 'Вторичный'

            # Декодируем название (исправляем кодировку)
            title_raw = item_data.get('title', '-')
            try:
                # Пробуем исправить кодировку
                title = title_raw.encode('latin1').decode('utf-8') if 'Ð' in title_raw else title_raw
            except:
                title = title_raw

            address_raw = item_data.get('address', '-')
            try:
                address = address_raw.encode('latin1').decode('utf-8') if 'Ð' in address_raw else address_raw
            except:
                address = address_raw

            # Формируем строку данных
            row = {
                'Название': title,
                'Стоимость': price,
                'Стоимость за метр': price_per_meter,
                'Тип жилья': property_type,
                'Тип рынка': market_type,
                'Адрес': address,
                'Количество комнат': params.get('Количество комнат', '-'),
                'Общая площадь(м²)': total_area,
                'Площадь кухни(м²)': kitchen_area,
                'Жилая площадь(м²)': living_area,
                'Этаж': current_floor,
                'Всего этажей': total_floors,
                'Высота потолков(м)': clean_number(params.get('Высота потолков', '-')),
                'Балкон': 'Да' if 'балкон' in str(params.get('Балкон', '')).lower() else '-',
                'Лоджия': 'Да' if 'лоджи' in str(params.get('Лоджия', '')).lower() else '-',
                'Санузел(Раздельный)': 'Да' if has_separate else '-',
                'Санузел(Совмещенный)': 'Да' if has_combined else '-',
                'Ремонт': params.get('Отделка', '-'),
                'Дата обновления': parse_russian_date(item_data.get('sortFormatedDate', '-')),
                'Просмотрено': total_views,
                'Год постройки': params.get('Год постройки', '-'),
                'Тип дома': params.get('Тип дома', '-'),
                'Название метро': station,
                'Путь до метро(мин)': metro_minutes,
                'Долгота': coords.get('lng', 0),
                'Широта': coords.get('lat', 0)
            }

            all_data.append(row)

            # Вывод информации (ИСПРАВЛЕНО: было 'Стоистоимость', теперь 'Стоимость')
            print(f"✅ {row['Название']}")
            print(f"   Цена: {row['Стоимость']:,} ₽".replace(',', ' '))
            print(f"   Площадь: {row['Общая площадь(м²)']} м²")
            print(f"   Цена за м²: {row['Стоимость за метр']:,} ₽".replace(',', ' '))
            print(f"   Адрес: {row['Адрес']}")
            print(f"   Метро: {row['Название метро']} ({row['Путь до метро(мин)']} мин)")
            print(f"   Просмотров: {row['Просмотрено']}")

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            errors += 1

        print(f"Прогресс: {i}/{len(all_offers)} | Ошибок: {errors}")
        i += 1

        # Пауза между запросами
        delay = random.uniform(3, 6)
        print(f"Пауза {delay:.1f} сек...")
        time.sleep(delay)

    driver.quit()

    # Создаем DataFrame
    df = pd.DataFrame(all_data)
    return df

# Основной блок
if __name__ == "__main__":
    # Сначала собираем ссылки (раскомментировать при первом запуске)
    # get_offers(2, 'moskva', 'link_test.json')

    # Парсим данные
    df = get_data_from_offers()

    # Сохраняем результаты
    df.to_csv('avito_apartments_test.csv', index=False, encoding='utf-8-sig')
    df.to_excel('avito_apartments.xlsx', index=False)

    print(f"\n✅ Собрано {len(df)} объявлений")
    print("\nПервые 5 строк:")
    print(df.head())