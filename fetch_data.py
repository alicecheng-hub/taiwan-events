#!/usr/bin/env python3
"""
fetch_data.py
- 棒球賽程 & 積分榜：LINE TODAY __NEXT_DATA__
- 演唱會：tickettw.com（只抓大型場館）
GitHub Actions 每天執行一次。

相依套件：pip install requests beautifulsoup4
"""

import json, re, os
from datetime import datetime
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

LINE_TODAY_SEASON = 'CPBL-2026-oB'

# 符合網頁篩選的大型場館關鍵字
TARGET_VENUES = [
    '台北大巨蛋', '大巨蛋',
    '台北小巨蛋', '小巨蛋',
    '高雄巨蛋', '高雄世運', '高雄流行音樂中心', '高雄海音館',
    '台中洲際', '台中巨蛋',
]

# ── 工具函式 ──────────────────────────────────────────────

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已儲存 {path}")

def get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=15, **kw)
    r.raise_for_status()
    return r

def next_data(url):
    soup = BeautifulSoup(get(url).text, 'html.parser')
    tag = soup.find('script', id='__NEXT_DATA__')
    if not tag:
        raise ValueError('找不到 __NEXT_DATA__')
    return json.loads(tag.string)

def is_target_venue(venue_str):
    return any(k in venue_str for k in TARGET_VENUES)

def normalize_venue(venue_str):
    """把場館名稱統一，方便前端篩選"""
    if '大巨蛋' in venue_str:
        return '台北大巨蛋'
    if '小巨蛋' in venue_str:
        return '台北小巨蛋'
    if '高雄巨蛋' in venue_str:
        return '高雄巨蛋'
    if '世運' in venue_str:
        return '高雄世運主場館'
    if '海音' in venue_str or '流行音樂中心' in venue_str:
        return '高雄流行音樂中心海音館'
    if '洲際' in venue_str and ('台中' in venue_str or '洲際' in venue_str):
        return '台中洲際棒球場'
    return venue_str

def parse_date(s):
    s = s.strip()
    m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    m2 = re.search(r'(\d{1,2})[/-](\d{1,2})', s)
    if m2:
        return f"{datetime.now().year}/{int(m2.group(1)):02d}/{int(m2.group(2)):02d}"
    return ''

def is_future(date_str):
    try:
        d = datetime.strptime(date_str, '%Y/%m/%d').date()
        return d >= datetime.now().date()
    except Exception:
        return False

# ── CPBL 積分 & 賽程（LINE TODAY）────────────────────────

TEAM_MAP = {
    '中信兄弟':'中信兄弟','統一7-ELEVEn獅':'統一獅','統一獅':'統一獅',
    '樂天桃猿':'樂天桃猿','富邦悍將':'富邦悍將','味全龍':'味全龍','台鋼雄鷹':'台鋼雄鷹',
}
STAD_MAP = {
    '台北大巨蛋':'大巨蛋','洲際棒球場':'洲際','澄清湖棒球場':'澄清湖',
    '亞太國際棒球場':'亞太','桃園國際棒球場':'桃園','新莊棒球場':'新莊',
    '斗六棒球場':'斗六','天母棒球場':'天母','嘉義市棒球場':'嘉義市',
}

def _team(n):
    for k,v in TEAM_MAP.items():
        if k in n: return v
    return n

def _stad(n):
    for k,v in STAD_MAP.items():
        if k in n: return v
    return n

def _pct(w,l,d):
    t=w+l+d; return f'.{round(w/t*1000):03d}' if t else '.000'


def fetch_cpbl():
    games = []
    try:
        ndata = next_data(f'https://today.line.me/tw/v3/baseball/seasons/{LINE_TODAY_SEASON}/schedule')
        days = ndata['props']['pageProps'].get('schedule',{}).get('days',[])
        for day in days:
            date_fmt = day.get('date','').replace('-','/')
            for g in day.get('games',[]):
                away = _team(g.get('awayTeam',{}).get('name',''))
                home = _team(g.get('homeTeam',{}).get('name',''))
                time = (g.get('startTime') or '18:05')[:5]
                stad = _stad(g.get('stadium',{}).get('name',''))
                if away and home:
                    games.append({'date':date_fmt,'time':time,'away':away,'home':home,'stadium':stad})
        print(f"  → 賽程 {len(games)} 場")
    except Exception as e:
        print(f"⚠️ 賽程失敗: {e}")
    return sorted(games, key=lambda x: x['date'])


def fetch_standings():
    standings, recent = [], []
    try:
        ndata = next_data(f'https://today.line.me/tw/v3/baseball/seasons/{LINE_TODAY_SEASON}/standings')
        teams = ndata['props']['pageProps'].get('standings',{}).get('teams',[])
        for i,t in enumerate(teams,1):
            w,l,d = t.get('wins',0), t.get('losses',0), t.get('draws',0)
            standings.append({'rank':i,'team':_team(t.get('name','')),'win':w,'loss':l,'draw':d,
                              'pct':_pct(w,l,d),'gb':str(t.get('gamesBack','-')),'streak':t.get('streak','')})
        print(f"  → 積分榜 {len(standings)} 隊")
    except Exception as e:
        print(f"⚠️ 積分榜失敗: {e}")

    try:
        ndata2 = next_data(f'https://today.line.me/tw/v3/baseball/seasons/{LINE_TODAY_SEASON}/schedule?tab=result')
        days = ndata2['props']['pageProps'].get('schedule',{}).get('days',[])
        for day in days[:5]:
            for g in day.get('games',[]):
                away = _team(g.get('awayTeam',{}).get('name',''))
                home = _team(g.get('homeTeam',{}).get('name',''))
                s1,s2 = g.get('awayScore'), g.get('homeScore')
                date_fmt = day.get('date','').replace('-','/')
                if away and home and s1 is not None:
                    recent.append({'date':date_fmt,'away':away,'away_score':s1,'home':home,'home_score':s2})
        print(f"  → 近期戰績 {len(recent)} 場")
    except Exception as e:
        print(f"⚠️ 近期戰績失敗: {e}")

    return standings, recent


# ── 演唱會（tickettw.com 多頁爬取）──────────────────────

def fetch_concerts():
    concerts = []
    page = 1
    seen = set()

    while True:
        url = f'https://www.tickettw.com/concerts?page={page}'
        try:
            soup = BeautifulSoup(get(url).text, 'html.parser')
        except Exception as e:
            print(f"⚠️ tickettw 第{page}頁失敗: {e}")
            break

        cards = soup.select('article, [class*="concert-card"], [class*="event-card"], [class*="concert-item"]')
        if not cards:
            break

        found_any_future = False
        for card in cards:
            title_el  = card.select_one('h2, h3, [class*="title"], [class*="name"]')
            date_el   = card.select_one('[class*="date"], time, [class*="time"]')
            venue_el  = card.select_one('[class*="venue"], [class*="location"], [class*="place"]')
            sale_el   = card.select_one('[class*="sale"], [class*="ticket"], [class*="open"]')
            sold_el   = card.select_one('[class*="sold-out"], [class*="soldout"]')
            link_el   = card.select_one('a[href]')

            if not title_el:
                continue

            title    = title_el.get_text(strip=True)
            date_str = parse_date(date_el.get_text(strip=True) if date_el else '')
            venue    = venue_el.get_text(strip=True) if venue_el else ''
            sale_raw = sale_el.get_text(strip=True) if sale_el else ''
            sold_out = bool(sold_el)
            href     = link_el['href'] if link_el else ''
            if href and not href.startswith('http'):
                href = 'https://www.tickettw.com' + href

            # 只要大型場館
            if not is_target_venue(venue):
                continue

            # 只要未來場次
            if not date_str or not is_future(date_str):
                continue

            found_any_future = True

            if title in seen:
                continue
            seen.add(title)

            # 解析售票狀態
            sale_date = ''
            if sold_out:
                sale_date = '已完售'
            elif '已開賣' in sale_raw or '售票中' in sale_raw:
                sale_date = '已開賣'
            elif sale_raw:
                # 嘗試抓開賣日期
                dm = re.search(r'(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})', sale_raw)
                sale_date = dm.group(1).replace('-','/') if dm else sale_raw[:20]
            else:
                sale_date = '待公布'

            concerts.append({
                'title':     title,
                'date':      date_str,
                'venue':     normalize_venue(venue),
                'sale_date': sale_date,
                'sold_out':  sold_out,
                'url':       href,
                'platform':  'tickettw',
            })

        # 如果整頁都沒有未來場次，停止翻頁
        if not found_any_future:
            break

        # 看有沒有下一頁
        next_btn = soup.select_one('a[rel="next"], [class*="next"]:not([class*="disabled"])')
        if not next_btn:
            break
        page += 1
        if page > 20:  # 最多20頁保險
            break

    print(f"  → 演唱會 {len(concerts)} 筆")
    return concerts if concerts else None


# ── 主程式 ────────────────────────────────────────────────

def main():
    print("🔄 開始抓取資料...")
    now = datetime.now().isoformat()

    print("\n📅 抓取 CPBL 賽程...")
    cpbl = fetch_cpbl()

    print("\n🏆 抓取積分榜...")
    standings, recent = fetch_standings()

    print("\n🎤 抓取演唱會（tickettw 大型場館）...")
    concerts = fetch_concerts()

    save('data/cpbl.json', {'updated': now, 'games': cpbl})
    save('data/standings.json', {'updated': now, 'standings': standings, 'recent': recent})

    if concerts is not None:
        save('data/concerts.json', {'updated': now, 'concerts': concerts})
    else:
        print("⏭ 演唱會爬蟲無資料，保留現有 concerts.json")

    print(f"\n✅ 完成！CPBL {len(cpbl)} 場，積分榜 {len(standings)} 隊，演唱會 {len(concerts) if concerts else '保留舊'} 筆")

if __name__ == '__main__':
    main()
