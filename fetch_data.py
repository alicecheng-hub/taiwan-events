#!/usr/bin/env python3
"""
fetch_data.py
爬取中華職棒賽程 & 台灣演唱會資訊，輸出 JSON 供前端使用。
GitHub Actions 每天執行一次。
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, date
import os

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

# ── 工具函式 ──────────────────────────────────────────────

def get(url, **kwargs):
    r = requests.get(url, headers=HEADERS, timeout=15, **kwargs)
    r.raise_for_status()
    return r

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已儲存 {path}（{len(data)} 筆）")

# ── CPBL 中華職棒賽程 ─────────────────────────────────────

def fetch_cpbl():
    """
    從 CPBL 官網爬取本月賽程。
    頁面結構：每個 .GameDate 內有多個 .game-item
    """
    games = []
    year = datetime.now().year

    # 爬本月 + 下個月
    for month_offset in range(0, 3):
        month = (datetime.now().month - 1 + month_offset) % 12 + 1
        y = year + ((datetime.now().month - 1 + month_offset) // 12)
        url = f'https://www.cpbl.com.tw/schedule/index?year={y}&month={month:02d}&kind=A'

        try:
            r = get(url)
        except Exception as e:
            print(f"⚠️ CPBL {y}/{month:02d} 失敗: {e}")
            continue

        soup = BeautifulSoup(r.text, 'html.parser')

        for date_block in soup.select('.GameDate, [class*="schedule-date"], [class*="game-date"]'):
            date_str = date_block.get_text(strip=True)
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_str)
            if not date_match:
                continue
            m, d = date_match.groups()
            game_date = f"{y}/{int(m):02d}/{int(d):02d}"

            for game in date_block.find_next_siblings(['div', 'li'], limit=20):
                if 'GameDate' in (game.get('class') or []):
                    break
                text = game.get_text(' ', strip=True)
                # 找隊名、時間、球場
                teams = re.findall(r'[\u4e00-\u9fff\w]+(?:兄弟|桃猿|獅|雄鷹|龍|悍將)', text)
                time_m = re.search(r'(\d{1,2}:\d{2})', text)
                stadium_m = re.search(r'(大巨蛋|洲際|澄清湖|亞太|桃園|新莊|斗六)', text)

                if len(teams) >= 2:
                    games.append({
                        'date': game_date,
                        'time': time_m.group(1) if time_m else '18:05',
                        'away': teams[0],
                        'home': teams[1],
                        'stadium': stadium_m.group(1) if stadium_m else '',
                    })

    # 若爬不到就用備用方式（解析另一個格式）
    if not games:
        games = fetch_cpbl_fallback(year)

    games.sort(key=lambda x: x['date'])
    return games


def fetch_cpbl_fallback(year):
    """備用：從 schedule JSON API 嘗試"""
    games = []
    try:
        # 部分球類網站有隱藏 JSON endpoint
        r = get(f'https://www.cpbl.com.tw/schedule/getgamelist?year={year}&kindCode=A')
        data = r.json()
        for item in data:
            games.append({
                'date': item.get('GameDate', ''),
                'time': item.get('StartTime', '18:05'),
                'away': item.get('AwayTeamName', ''),
                'home': item.get('HomeTeamName', ''),
                'stadium': item.get('StadiumName', ''),
            })
    except Exception as e:
        print(f"⚠️ CPBL fallback 也失敗: {e}")
    return games


# ── 演唱會資訊 ────────────────────────────────────────────

def fetch_concerts():
    """
    從 tickettw.com 爬取台灣演唱會列表。
    """
    concerts = []

    try:
        r = get('https://www.tickettw.com/')
        soup = BeautifulSoup(r.text, 'html.parser')

        # tickettw 結構：每個演唱會是一個 card
        for card in soup.select('.event-card, .concert-item, article, [class*="event"]'):
            title = card.select_one('h2, h3, .title, [class*="title"]')
            date_el = card.select_one('.date, [class*="date"], time')
            venue_el = card.select_one('.venue, [class*="venue"], [class*="location"]')
            sale_el = card.select_one('[class*="sale"], [class*="ticket"]')
            link_el = card.select_one('a[href]')

            if not title:
                continue

            concerts.append({
                'title': title.get_text(strip=True),
                'date': date_el.get_text(strip=True) if date_el else '',
                'venue': venue_el.get_text(strip=True) if venue_el else '',
                'sale_date': sale_el.get_text(strip=True) if sale_el else '',
                'url': link_el['href'] if link_el else '',
            })

    except Exception as e:
        print(f"⚠️ tickettw 失敗: {e}")

    # 若失敗，試 kktix
    if not concerts:
        concerts = fetch_concerts_kktix()

    return concerts


def fetch_concerts_kktix():
    """備用：爬 KKTIX 台灣活動"""
    concerts = []
    try:
        r = get('https://kktix.com/g/taiwan')
        soup = BeautifulSoup(r.text, 'html.parser')

        for card in soup.select('.event-card, [class*="EventCard"], [class*="event-item"]'):
            title = card.select_one('h3, h2, .name, [class*="name"]')
            date_el = card.select_one('.date, [class*="date"]')
            venue_el = card.select_one('.location, [class*="location"]')
            link_el = card.select_one('a[href]')

            if not title:
                continue

            href = link_el['href'] if link_el else ''
            if href and not href.startswith('http'):
                href = 'https://kktix.com' + href

            concerts.append({
                'title': title.get_text(strip=True),
                'date': date_el.get_text(strip=True) if date_el else '',
                'venue': venue_el.get_text(strip=True) if venue_el else '',
                'sale_date': '',
                'url': href,
            })
    except Exception as e:
        print(f"⚠️ KKTIX 也失敗: {e}")

    return concerts


# ── 主程式 ────────────────────────────────────────────────

def main():
    print("🔄 開始抓取資料...")
    now = datetime.now().isoformat()

    print("\n📅 抓取 CPBL 賽程...")
    cpbl = fetch_cpbl()

    print("\n🎤 抓取演唱會資訊...")
    concerts = fetch_concerts()

    save('data/cpbl.json', {
        'updated': now,
        'games': cpbl
    })

    save('data/concerts.json', {
        'updated': now,
        'concerts': concerts
    })

    print(f"\n✅ 完成！CPBL {len(cpbl)} 場，演唱會 {len(concerts)} 筆")


if __name__ == '__main__':
    main()
