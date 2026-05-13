#!/usr/bin/env python3
"""
fetch_data.py
爬取中華職棒賽程 & 台灣演唱會資訊，輸出 JSON 供前端使用。
GitHub Actions 每天執行一次。

相依套件：
  pip install playwright beautifulsoup4 requests
  playwright install chromium --with-deps
"""

import json
import re
import os
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

# ── 工具函式 ──────────────────────────────────────────────

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已儲存 {path}")

def get_page_html(url, wait='networkidle', timeout=30000):
    """用 Playwright 開啟頁面並回傳 HTML（可跑 JavaScript 的網站用這個）"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS['User-Agent'],
            locale='zh-TW',
        )
        page = ctx.new_page()
        page.goto(url, wait_until=wait, timeout=timeout)
        html = page.content()
        browser.close()
    return html

def get_requests(url):
    """一般靜態網站用 requests"""
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text

# ── CPBL 積分榜（Playwright）────────────────────────────

def fetch_standings():
    standings = []
    recent = []

    try:
        print("  → 爬取積分榜...")
        html = get_page_html('https://www.cpbl.com.tw/standings/season')
        soup = BeautifulSoup(html, 'html.parser')

        # 積分榜表格
        rows = soup.select('table tbody tr') or soup.select('table tr')[1:]
        for i, row in enumerate(rows, 1):
            cols = [td.get_text(strip=True) for td in row.select('td')]
            if len(cols) < 5:
                continue
            # 過濾空行
            if not cols[0] or cols[0].isdigit():
                continue
            team_name = cols[0]
            try:
                w   = int(re.search(r'\d+', cols[1]).group()) if re.search(r'\d+', cols[1]) else 0
                l   = int(re.search(r'\d+', cols[2]).group()) if re.search(r'\d+', cols[2]) else 0
                d   = int(re.search(r'\d+', cols[3]).group()) if re.search(r'\d+', cols[3]) else 0
                pct = cols[4]
                gb  = cols[5] if len(cols) > 5 else '-'
                streak = cols[-1] if len(cols) > 6 else ''
            except Exception:
                continue
            standings.append({
                'rank':   i,
                'team':   team_name,
                'win':    w,
                'loss':   l,
                'draw':   d,
                'pct':    pct,
                'gb':     gb,
                'streak': streak,
            })
        print(f"  → 積分榜：{len(standings)} 隊")
    except Exception as e:
        print(f"⚠️ 積分榜失敗: {e}")

    try:
        print("  → 爬取近期戰績...")
        html2 = get_page_html('https://www.cpbl.com.tw/schedule/result')
        soup2 = BeautifulSoup(html2, 'html.parser')
        for game in soup2.select('.GameResult, [class*="result-item"], [class*="game-result"]')[:15]:
            text = game.get_text(' ', strip=True)
            teams  = re.findall(r'(中信兄弟|統一[七7]?-?ELEVEn?獅|統一獅|樂天桃猿|富邦悍將|味全龍|台鋼雄鷹)', text)
            scores = re.findall(r'\b(\d{1,2})\b', text)
            date_m = re.search(r'(\d{4}/\d{2}/\d{2}|\d{4}-\d{2}-\d{2})', text)
            if len(teams) >= 2 and len(scores) >= 2 and date_m:
                recent.append({
                    'date':       date_m.group(1).replace('-', '/'),
                    'away':       _normalize_team(teams[0]),
                    'away_score': int(scores[0]),
                    'home':       _normalize_team(teams[1]),
                    'home_score': int(scores[1]),
                })
        print(f"  → 近期戰績：{len(recent)} 場")
    except Exception as e:
        print(f"⚠️ 近期戰績失敗: {e}")

    return standings, recent

def _normalize_team(name):
    """統一不同寫法的隊名"""
    if '統一' in name:
        return '統一獅'
    return name

# ── CPBL 賽程（Playwright）──────────────────────────────

def fetch_cpbl():
    games = []
    now = datetime.now()

    for month_offset in range(0, 3):
        m_abs = now.month - 1 + month_offset
        month = m_abs % 12 + 1
        year  = now.year + m_abs // 12
        url = f'https://www.cpbl.com.tw/schedule/index?year={year}&month={month:02d}&kind=A'
        try:
            print(f"  → 爬取賽程 {year}/{month:02d}...")
            html = get_page_html(url)
            soup = BeautifulSoup(html, 'html.parser')

            # 逐日區塊解析
            for block in soup.select('[class*="GameDate"], [class*="date-block"], [class*="schedule-date"]'):
                date_text = block.get_text(' ', strip=True)
                dm = re.search(r'(\d{1,2})[/月](\d{1,2})', date_text)
                if not dm:
                    continue
                game_date = f"{year}/{int(dm.group(1)):02d}/{int(dm.group(2)):02d}"

                # 同一個 block 內的多場比賽
                for item in block.select('[class*="game"], [class*="Game"], li'):
                    t = item.get_text(' ', strip=True)
                    teams   = re.findall(r'(中信兄弟|統一獅|樂天桃猿|富邦悍將|味全龍|台鋼雄鷹)', t)
                    time_m  = re.search(r'(\d{1,2}:\d{2})', t)
                    stad_m  = re.search(r'(大巨蛋|洲際|澄清湖|亞太|桃園|新莊|斗六|天母)', t)
                    if len(teams) >= 2:
                        games.append({
                            'date':    game_date,
                            'time':    time_m.group(1) if time_m else '18:05',
                            'away':    teams[0],
                            'home':    teams[1],
                            'stadium': stad_m.group(1) if stad_m else '',
                        })
        except Exception as e:
            print(f"⚠️ 賽程 {year}/{month:02d} 失敗: {e}")

    games.sort(key=lambda x: x['date'])
    print(f"  → 賽程共 {len(games)} 場")
    return games

# ── 演唱會（requests，靜態較多）────────────────────────

def fetch_concerts():
    concerts = []

    # --- KKTIX ---
    try:
        print("  → 爬取 KKTIX...")
        html = get_requests('https://kktix.com/g/taiwan')
        soup = BeautifulSoup(html, 'html.parser')
        for card in soup.select('[class*="EventCard"], [class*="event-card"], [class*="event-item"]'):
            title  = card.select_one('h3, h2, [class*="name"], [class*="title"]')
            date_e = card.select_one('[class*="date"], time')
            venue_e= card.select_one('[class*="location"], [class*="venue"]')
            link_e = card.select_one('a[href]')
            sold_e = card.select_one('[class*="sold"], [class*="soldout"]')
            if not title:
                continue
            href = link_e['href'] if link_e else ''
            if href and not href.startswith('http'):
                href = 'https://kktix.com' + href
            concerts.append({
                'title':     title.get_text(strip=True),
                'date':      _parse_date(date_e.get_text(strip=True) if date_e else ''),
                'venue':     venue_e.get_text(strip=True) if venue_e else '',
                'sale_date': '已開賣',
                'sold_out':  bool(sold_e),
                'url':       href,
                'platform':  'KKTIX',
            })
        print(f"  → KKTIX：{len(concerts)} 筆")
    except Exception as e:
        print(f"⚠️ KKTIX 失敗: {e}")

    # --- 拓元 tixcraft ---
    try:
        print("  → 爬取 tixcraft...")
        html2 = get_requests('https://tixcraft.com/activity/area/tw')
        soup2 = BeautifulSoup(html2, 'html.parser')
        before = len(concerts)
        for card in soup2.select('[class*="activity-item"], [class*="event"], article'):
            title  = card.select_one('h3, h2, [class*="title"], [class*="name"]')
            date_e = card.select_one('[class*="date"], time')
            venue_e= card.select_one('[class*="venue"], [class*="location"]')
            link_e = card.select_one('a[href]')
            sold_e = card.select_one('[class*="sold"], [class*="soldout"]')
            if not title:
                continue
            href = link_e['href'] if link_e else ''
            if href and not href.startswith('http'):
                href = 'https://tixcraft.com' + href
            concerts.append({
                'title':     title.get_text(strip=True),
                'date':      _parse_date(date_e.get_text(strip=True) if date_e else ''),
                'venue':     venue_e.get_text(strip=True) if venue_e else '',
                'sale_date': '已開賣',
                'sold_out':  bool(sold_e),
                'url':       href,
                'platform':  '拓元',
            })
        print(f"  → 拓元：{len(concerts)-before} 筆")
    except Exception as e:
        print(f"⚠️ 拓元失敗: {e}")

    # 去除無日期或重複標題
    seen = set()
    filtered = []
    for c in concerts:
        if not c['date'] or c['title'] in seen:
            continue
        seen.add(c['title'])
        filtered.append(c)

    return filtered

def _parse_date(s):
    """嘗試把各種日期字串轉成 YYYY/MM/DD"""
    s = s.strip()
    # 2026/05/15 或 2026-05-15
    m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    # 05/15
    m2 = re.search(r'(\d{1,2})/(\d{1,2})', s)
    if m2:
        return f"{datetime.now().year}/{int(m2.group(1)):02d}/{int(m2.group(2)):02d}"
    return ''

# ── 主程式 ────────────────────────────────────────────────

def main():
    print("🔄 開始抓取資料...")
    now = datetime.now().isoformat()

    print("\n📅 抓取 CPBL 賽程...")
    cpbl = fetch_cpbl()

    print("\n🏆 抓取積分榜...")
    standings, recent = fetch_standings()

    print("\n🎤 抓取演唱會資訊...")
    concerts = fetch_concerts()

    save('data/cpbl.json', {'updated': now, 'games': cpbl})
    save('data/standings.json', {'updated': now, 'standings': standings, 'recent': recent})
    save('data/concerts.json', {'updated': now, 'concerts': concerts})

    print(f"\n✅ 完成！CPBL {len(cpbl)} 場，積分榜 {len(standings)} 隊，演唱會 {len(concerts)} 筆")

if __name__ == '__main__':
    main()
