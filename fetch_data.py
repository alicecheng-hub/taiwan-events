#!/usr/bin/env python3
"""
fetch_data.py
- 棒球賽程：LINE TODAY HTML 文字解析（已驗證可抓到 269 場）
- 積分榜：ESPN CPBL API
- 演唱會：tickettw.com 文字 regex 解析（已確認資料格式）
相依套件：pip install requests beautifulsoup4
"""

import json, re, os
from datetime import datetime, date
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

SEASON   = 'CPBL-2026-oB'
TODAY    = date.today()
CUR_YEAR = TODAY.year

TEAMS = ['中信兄弟','統一獅','統一7-ELEVEn獅','樂天桃猿','富邦悍將','味全龍','台鋼雄鷹']
TEAM_NORM = {'統一7-ELEVEn獅':'統一獅','統一7-eleven獅':'統一獅','統一7-ELEVEn':'統一獅'}

TARGET_VENUES = ['台北大巨蛋','大巨蛋','台北小巨蛋','小巨蛋',
                 '高雄巨蛋','高雄世運','高雄流行音樂','海音館',
                 '台中洲際','台中巨蛋']

# ── 工具 ──────────────────────────────────────────────────

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 儲存 {path}")

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    return soup.get_text('\n')

def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def norm_team(n):
    for k, v in TEAM_NORM.items():
        if k in n: return v
    return n

def norm_venue(v):
    if '大巨蛋' in v: return '大巨蛋'
    if '小巨蛋' in v: return '小巨蛋'
    if '高雄巨蛋' in v: return '高雄巨蛋'
    if '世運' in v: return '高雄世運'
    if '澄清湖' in v: return '澄清湖'
    if '亞太' in v: return '亞太'
    if '洲際' in v: return '洲際'
    if '桃園' in v: return '桃園'
    if '新莊' in v: return '新莊'
    if '天母' in v: return '天母'
    if '斗六' in v: return '斗六'
    if '嘉義' in v: return '嘉義市'
    return v.strip()

def parse_tw_date(s):
    """解析 '2026年5月16日' → '2026/05/16'"""
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', s)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    m2 = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m2:
        return f"{m2.group(1)}/{int(m2.group(2)):02d}/{int(m2.group(3)):02d}"
    return ''

def is_future(date_str):
    try:
        return datetime.strptime(date_str, '%Y/%m/%d').date() >= TODAY
    except: return False

# ── CPBL 賽程（LINE TODAY）────────────────────────────────

def fetch_cpbl():
    games = []
    url = f'https://today.line.me/tw/v3/baseball/seasons/{SEASON}/schedule'
    try:
        text = fetch_text(url)
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        current_date = ''
        i = 0
        while i < len(lines):
            line = lines[i]

            # 日期行：M/D
            if re.fullmatch(r'\d{1,2}/\d{1,2}', line):
                parts = line.split('/')
                current_date = f"{CUR_YEAR}/{int(parts[0]):02d}/{int(parts[1]):02d}"
                i += 1
                continue

            # 時間行：HH:MM
            if re.fullmatch(r'\d{1,2}:\d{2}', line) and current_date:
                time_str = line
                venue, found_teams = '', []
                for j in range(i+1, min(i+15, len(lines))):
                    c = lines[j]
                    if not venue and any(k in c for k in
                        ['巨蛋','洲際','澄清湖','亞太','桃園','新莊','天母','斗六','嘉義','世運']):
                        venue = c
                    for t in TEAMS:
                        nt = norm_team(t)
                        if t in c and nt not in found_teams:
                            found_teams.append(nt)
                            break
                    if len(found_teams) == 2:
                        break

                if len(found_teams) == 2 and is_future(current_date):
                    games.append({
                        'date': current_date, 'time': time_str,
                        'away': found_teams[0], 'home': found_teams[1],
                        'stadium': norm_venue(venue),
                    })
            i += 1

        # 去重
        seen, out = set(), []
        for g in games:
            key = f"{g['date']}{g['time']}{g['away']}{g['home']}"
            if key not in seen:
                seen.add(key); out.append(g)

        print(f"  → 賽程 {len(out)} 場")
        return sorted(out, key=lambda x: (x['date'], x['time']))
    except Exception as e:
        print(f"⚠️ 賽程失敗: {e}")
        return []

# ── CPBL 積分榜（ESPN API）───────────────────────────────

ESPN_TEAM_MAP = {
    'Brothers':  '中信兄弟',
    'Lions':     '統一獅',
    'Monkeys':   '樂天桃猿',
    'Guardians': '富邦悍將',
    'Dragons':   '味全龍',
    'Hawks':     '台鋼雄鷹',
    'ELEVEn':    '統一獅',
    # 中文也可能出現
    '中信兄弟':  '中信兄弟',
    '統一':      '統一獅',
    '樂天':      '樂天桃猿',
    '富邦':      '富邦悍將',
    '味全':      '味全龍',
    '台鋼':      '台鋼雄鷹',
}

def map_espn_team(name):
    for k, v in ESPN_TEAM_MAP.items():
        if k in name: return v
    return name

def fetch_standings():
    standings, recent = [], []

    # 試 ESPN API
    espn_urls = [
        f'https://site.api.espn.com/apis/v2/sports/baseball/cpbl/standings?season={CUR_YEAR}',
        f'https://site.api.espn.com/apis/site/v2/sports/baseball/cpbl/standings?season={CUR_YEAR}',
        f'https://sports.core.api.espn.com/v2/sports/baseball/leagues/cpbl/seasons/{CUR_YEAR}/types/2/groups/1/standings/0',
    ]
    for url in espn_urls:
        try:
            data = fetch_json(url)
            # 嘗試解析不同的 ESPN 回傳格式
            entries = (data.get('standings', {}).get('entries', []) or
                       data.get('children', [{}])[0].get('standings', {}).get('entries', []) or
                       data.get('entries', []))
            for i, entry in enumerate(entries, 1):
                team_name = (entry.get('team', {}).get('displayName', '') or
                             entry.get('team', {}).get('name', ''))
                team = map_espn_team(team_name)
                stats = {s.get('name', ''): s.get('value', 0)
                         for s in entry.get('stats', [])}
                w = int(stats.get('wins', stats.get('W', 0)))
                l = int(stats.get('losses', stats.get('L', 0)))
                d = int(stats.get('ties', stats.get('D', 0)))
                tot = w + l + d
                pct = f'.{round(w/tot*1000):03d}' if tot else '.000'
                gb  = str(stats.get('gamesBehind', stats.get('GB', '-')))
                standings.append({'rank': i, 'team': team,
                                  'win': w, 'loss': l, 'draw': d,
                                  'pct': pct, 'gb': gb, 'streak': ''})
            if standings:
                print(f"  → 積分榜 {len(standings)} 隊（ESPN）")
                break
        except Exception as e:
            continue

    if not standings:
        # 備用：用 LINE TODAY 近期結果頁推算
        try:
            standings, recent = fetch_standings_from_results()
        except Exception as e:
            print(f"⚠️ 積分榜所有方法均失敗，保留舊資料")

    return standings, recent


def fetch_standings_from_results():
    """從 LINE TODAY 賽果計算積分"""
    standings = []
    recent    = []

    wins   = {t: 0 for t in ['中信兄弟','統一獅','樂天桃猿','富邦悍將','味全龍','台鋼雄鷹']}
    losses = {t: 0 for t in wins}
    draws  = {t: 0 for t in wins}

    text  = fetch_text(f'https://today.line.me/tw/v3/baseball/seasons/{SEASON}/schedule')
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    cur_date = ''
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.fullmatch(r'\d{1,2}/\d{1,2}', line):
            parts = line.split('/')
            cur_date = f"{CUR_YEAR}/{int(parts[0]):02d}/{int(parts[1]):02d}"
        # 找已完成比賽：有「賽事回顧」且在過去
        if '賽事回顧' in line and cur_date and not is_future(cur_date):
            # 在附近找兩支球隊和兩個比分
            chunk = lines[max(0, i-12):i]
            teams, scores = [], []
            for c in chunk:
                for t in ['中信兄弟','統一獅','統一7-ELEVEn獅','樂天桃猿','富邦悍將','味全龍','台鋼雄鷹']:
                    nt = norm_team(t)
                    if t in c and nt not in teams:
                        teams.append(nt)
                if re.fullmatch(r'\d{1,2}', c):
                    scores.append(int(c))
            if len(teams) == 2 and len(scores) >= 2:
                away, home = teams[0], teams[1]
                as_, hs_ = scores[-2], scores[-1]
                if away in wins:
                    if as_ > hs_: wins[away]+=1; losses[home]+=1
                    elif hs_ > as_: wins[home]+=1; losses[away]+=1
                    else: draws[away]+=1; draws[home]+=1
                if len(recent) < 15:
                    recent.append({'date': cur_date, 'away': away, 'away_score': as_,
                                   'home': home, 'home_score': hs_})
        i += 1

    # 計算積分榜
    all_teams = [(t, wins[t], losses[t], draws[t]) for t in wins]
    all_teams.sort(key=lambda x: (-x[1], x[2]))
    leader_w = all_teams[0][1] if all_teams else 0
    leader_l = all_teams[0][2] if all_teams else 0

    for rank, (team, w, l, d) in enumerate(all_teams, 1):
        tot = w + l + d
        pct = f'.{round(w/tot*1000):03d}' if tot else '.000'
        gb  = str(round(((leader_w - w) + (l - leader_l)) / 2, 1)) if rank > 1 else '-'
        standings.append({'rank': rank, 'team': team,
                          'win': w, 'loss': l, 'draw': d,
                          'pct': pct, 'gb': gb, 'streak': ''})

    print(f"  → 積分榜 {len(standings)} 隊（從賽果計算）")
    return standings, recent

# ── 演唱會（tickettw.com regex 解析）────────────────────

def fetch_concerts():
    concerts = []
    seen = set()

    for page in range(1, 11):  # 最多10頁
        url = f'https://www.tickettw.com/concerts?page={page}'
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            text = soup.get_text('\n')
        except Exception as e:
            print(f"  ⚠️ tickettw 第{page}頁失敗: {e}")
            break

        # 每筆演唱會資料的 regex 提取
        # 結構：標題 ... 演出日期: X 門票價錢: X 演出場館: X (優先購票: X)? 全面開賣: X
        # 從 <a href="/concert-ticket/XXX"> 連結取得各筆資料
        links = soup.select('a[href*="/concert-ticket/"]')
        if not links:
            print(f"  → 第{page}頁無演唱會連結，停止")
            break

        page_has_future = False

        for link in links:
            href = 'https://www.tickettw.com' + link['href']
            block = link.get_text(' ', strip=True)

            # 標題：演出日期前的文字，去掉「圖片」
            title_raw = re.split(r'演出日期', block)[0]
            title = re.sub(r'\s*圖片\s*', '', title_raw)
            title = re.sub(r'\|.*', '', title).strip()
            # 去掉重複（常見格式：「BABYMONSTER 台北演唱會 2026 BABYMONSTER 台北演唱會 2026」）
            half = len(title) // 2
            if title[:half].strip() == title[half:].strip():
                title = title[:half].strip()
            if not title or title in seen:
                continue

            # 演出日期
            date_m = re.search(r'演出日期[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日)', block)
            if not date_m:
                continue
            date_str = parse_tw_date(date_m.group(1))
            if not date_str or not is_future(date_str):
                continue

            # 演出場館
            venue_m = re.search(r'演出場館[:：]\s*([^\n門票全面優先⏰🔔]+)', block)
            venue = venue_m.group(1).strip() if venue_m else ''
            # 清理場館文字後面跟著的雜訊
            venue = re.split(r'[全優⏰🔔]', venue)[0].strip()

            if not any(kw in venue for kw in TARGET_VENUES):
                continue

            # 全面開賣
            sale_m = re.search(r'全面開賣[:：]\s*([^\n⏰🔔]+)', block)
            sale_raw = sale_m.group(1).strip() if sale_m else ''
            if '有待公佈' in sale_raw or not sale_raw:
                sale_date = '待公布'
            else:
                # 嘗試提取日期 + 平台
                sd_m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', sale_raw)
                platform_m = re.search(r'(KKTIX|TIXCRAFT|TICKET PLUS|IBON|寬宏|年代|friDay|Weverse)', sale_raw, re.I)
                if sd_m:
                    sale_date = parse_tw_date(sd_m.group(1))
                    if platform_m:
                        sale_date += f' {platform_m.group(1).upper()}'
                else:
                    sale_date = '已開賣'

            # 售票平台（取最後出現的已知平台）
            platform_found = re.findall(
                r'(KKTIX|TIXCRAFT|TICKET PLUS|IBON|寬宏|年代|friDay|Weverse)', block, re.I)
            platform = platform_found[-1].upper() if platform_found else 'tickettw'

            sold_out = '已完售' in block or 'sold out' in block.lower()
            if sold_out:
                sale_date = '已完售'

            page_has_future = True
            seen.add(title)
            concerts.append({
                'title':     title,
                'date':      date_str,
                'venue':     norm_venue(venue),
                'sale_date': sale_date,
                'sold_out':  sold_out,
                'url':       href,
                'platform':  platform,
            })

        if not page_has_future:
            print(f"  → 第{page}頁無未來場次，停止")
            break

    print(f"  → 演唱會 {len(concerts)} 筆")
    return concerts if concerts else None

# ── 主程式 ────────────────────────────────────────────────

def main():
    print("🔄 開始抓取資料...")
    now = datetime.now().isoformat()

    print("\n📅 CPBL 賽程...")
    cpbl = fetch_cpbl()

    print("\n🏆 CPBL 積分榜...")
    standings, recent = fetch_standings()

    print("\n🎤 演唱會（tickettw）...")
    concerts = fetch_concerts()

    save('data/cpbl.json', {'updated': now, 'games': cpbl})

    if standings:
        save('data/standings.json', {'updated': now, 'standings': standings, 'recent': recent})
    else:
        old = load_json('data/standings.json') or {}
        old.update({'updated': now, 'recent': recent or old.get('recent', [])})
        save('data/standings.json', old)
        print("  → 積分榜保留舊資料")

    if concerts:
        save('data/concerts.json', {'updated': now, 'concerts': concerts})
    else:
        print("  → 演唱會保留現有資料")

    print(f"\n✅ 完成！賽程 {len(cpbl)} 場，積分榜 {len(standings)} 隊，演唱會 {len(concerts) if concerts else '保留舊'} 筆")

if __name__ == '__main__':
    main()
