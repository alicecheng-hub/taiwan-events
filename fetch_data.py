#!/usr/bin/env python3
"""
fetch_data.py
- 棒球賽程：LINE TODAY 解析 <a href="*/games/*"> 標籤，每月分開抓
- 積分榜：從已結束比賽自行計算
- 演唱會：tickettw.com regex 解析
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

TEAM_LIST = ['中信兄弟','統一獅','統一7-ELEVEn獅','樂天桃猿','富邦悍將','味全龍','台鋼雄鷹']
TEAM_NORM = {'統一7-ELEVEn獅':'統一獅','統一7-eleven獅':'統一獅','統一7-ELEVEn':'統一獅'}
TEAM_SHORT = ['中信兄弟','統一獅','樂天桃猿','富邦悍將','味全龍','台鋼雄鷹']

TARGET_VENUES = [
    '台北大巨蛋','大巨蛋',
    '台北小巨蛋','小巨蛋',
    '高雄巨蛋',
    '高雄世運','世運主場館','世運',
    '高雄流行音樂中心','海音館','流行音樂中心',
    '台中洲際','台中巨蛋','台中流行音樂中心',
]

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

def fetch_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')

def norm_team(n):
    for k, v in TEAM_NORM.items():
        if k in n: return v
    return n

def norm_venue(v):
    v = v.strip()
    if '大巨蛋' in v and '小' not in v: return '台北大巨蛋'
    if '小巨蛋' in v: return '台北小巨蛋'
    if '高雄巨蛋' in v: return '高雄巨蛋'
    if '世運' in v: return '高雄世運主場館'
    if '海音' in v or '流行音樂中心' in v: return '高雄流行音樂中心海音館'
    if '澄清湖' in v: return '澄清湖'
    if '亞太' in v: return '亞太'
    if '台中' in v and ('洲際' in v or '巨蛋' in v or '流行' in v): return '台中'
    if '洲際' in v: return '洲際'
    if '桃園' in v: return '桃園'
    if '新莊' in v: return '新莊'
    if '天母' in v: return '天母'
    if '斗六' in v: return '斗六'
    if '嘉義' in v: return '嘉義市'
    return v

def parse_tw_date(s):
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', s)
    if m: return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m: return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    return ''

def is_future(date_str):
    try: return datetime.strptime(date_str, '%Y/%m/%d').date() >= TODAY
    except: return False

def is_past(date_str):
    try: return datetime.strptime(date_str, '%Y/%m/%d').date() < TODAY
    except: return False

# ── 解析單個 <a> game 連結 ────────────────────────────────

def parse_game_link(a_tag, cur_date):
    """從 LINE TODAY 的 <a href='*/games/*'> 解析一場比賽"""
    # 取得 a 標籤內的純文字，過濾掉 img alt
    lines = []
    for child in a_tag.descendants:
        if child.name == 'img':
            continue  # 跳過圖片
        if hasattr(child, 'string') and child.string:
            t = child.string.strip()
            if t:
                lines.append(t)

    # 去重複並過濾雜訊
    clean = []
    seen = set()
    for l in lines:
        if l not in seen and l != 'team-icon':
            seen.add(l)
            clean.append(l)

    time_str, venue, teams = '', '', []
    for l in clean:
        if re.fullmatch(r'\d{1,2}:\d{2}', l):
            time_str = l
        elif any(k in l for k in ['巨蛋','洲際','澄清湖','亞太','桃園','新莊','天母','斗六','嘉義','世運','樂天桃園']):
            if not venue:
                venue = l
        else:
            for t in TEAM_LIST:
                nt = norm_team(t)
                if t in l and nt not in teams:
                    teams.append(nt)
                    break

    if len(teams) == 2 and time_str and cur_date:
        return {
            'date':    cur_date,
            'time':    time_str,
            'away':    teams[0],
            'home':    teams[1],
            'stadium': norm_venue(venue),
        }
    return None

# ── CPBL 賽程（LINE TODAY，每月分開抓）──────────────────

def fetch_cpbl_month(month):
    """抓指定月份的賽程"""
    url = f'https://today.line.me/tw/v3/baseball/seasons/{SEASON}/schedule'
    # LINE TODAY 預設顯示當月，我們用 #month 或其他方式取得；
    # 由於是 SSR，直接抓主頁面會拿到當前月份資料
    try:
        soup = fetch_soup(url)
    except Exception as e:
        print(f"  ⚠️ LINE TODAY 月份 {month} 失敗: {e}")
        return [], []

    games_future, games_past = [], []
    cur_date = ''

    # 遍歷整個文件樹，按順序處理元素
    for elem in soup.find_all(True):
        text = elem.get_text(strip=True)

        # 日期 header（格式：M/D，例如 5/13）
        if (elem.name in ['h2','h3','h4','div','span','p'] and
                re.fullmatch(r'\d{1,2}/\d{1,2}', text)):
            parts = text.split('/')
            cur_date = f"{CUR_YEAR}/{int(parts[0]):02d}/{int(parts[1]):02d}"

        # 比賽連結
        elif elem.name == 'a' and '/games/' in (elem.get('href') or ''):
            game = parse_game_link(elem, cur_date)
            if game:
                if is_future(game['date']):
                    games_future.append(game)
                elif is_past(game['date']):
                    games_past.append(game)

    return games_future, games_past


def fetch_cpbl():
    print("  → 抓取 LINE TODAY 賽程（當月）...")
    games_future, games_past = fetch_cpbl_month(TODAY.month)

    # 去重
    def dedup(lst):
        seen, out = set(), []
        for g in lst:
            k = f"{g['date']}{g['time']}{g['away']}{g['home']}"
            if k not in seen:
                seen.add(k); out.append(g)
        return sorted(out, key=lambda x: (x['date'], x['time']))

    gf = dedup(games_future)
    gp = dedup(games_past)
    print(f"  → 未來賽程 {len(gf)} 場，過去 {len(gp)} 場（含比分待計算）")
    return gf, gp

# ── CPBL 積分榜（從過去比賽計算）────────────────────────

def fetch_scores_for_standings():
    """
    從 LINE TODAY 逐月頁面抓過去比賽的比分
    比賽連結格式：/games/XXX，點進去有比分
    這裡改從頁面文字掃描「X:Y」格式
    """
    url = f'https://today.line.me/tw/v3/baseball/seasons/{SEASON}/schedule'
    try:
        soup = fetch_soup(url)
        text = soup.get_text('\n')
        lines = [l.strip() for l in text.splitlines() if l.strip()]
    except Exception as e:
        print(f"  ⚠️ 積分榜資料抓取失敗: {e}")
        return []

    results = []
    cur_date = ''
    i = 0
    while i < len(lines):
        l = lines[i]
        # 日期
        if re.fullmatch(r'\d{1,2}/\d{1,2}', l):
            parts = l.split('/')
            cur_date = f"{CUR_YEAR}/{int(parts[0]):02d}/{int(parts[1]):02d}"
        # 比分行：「X : Y」或相鄰兩個單獨數字
        # LINE TODAY 已結束的比賽顯示比分在兩隊名稱之間
        if cur_date and is_past(cur_date):
            # 找連續的：隊名 數字 數字 隊名
            teams, scores = [], []
            for j in range(max(0, i-5), min(len(lines), i+8)):
                c = lines[j]
                if re.fullmatch(r'\d{1,2}', c):
                    scores.append(int(c))
                for t in TEAM_LIST:
                    nt = norm_team(t)
                    if t in c and nt not in teams:
                        teams.append(nt)
            if len(teams) == 2 and len(scores) >= 2:
                key = f"{cur_date}{teams[0]}{teams[1]}"
                if not any(r.get('_key') == key for r in results):
                    results.append({
                        '_key': key,
                        'date': cur_date,
                        'away': teams[0], 'away_score': scores[0],
                        'home': teams[1], 'home_score': scores[1],
                    })
        i += 1
    return results


def calc_standings(game_results):
    wins   = {t: 0 for t in TEAM_SHORT}
    losses = {t: 0 for t in TEAM_SHORT}
    draws  = {t: 0 for t in TEAM_SHORT}
    last5  = {t: [] for t in TEAM_SHORT}

    for g in sorted(game_results, key=lambda x: x.get('date','')):
        away, home = g['away'], g['home']
        as_, hs_   = g.get('away_score',0), g.get('home_score',0)
        if away not in wins or home not in wins:
            continue
        if as_ > hs_:
            wins[away]+=1; losses[home]+=1
            last5[away].append('W'); last5[home].append('L')
        elif hs_ > as_:
            wins[home]+=1; losses[away]+=1
            last5[home].append('W'); last5[away].append('L')
        else:
            draws[away]+=1; draws[home]+=1
            last5[away].append('D'); last5[home].append('D')

    all_t = [(t, wins[t], losses[t], draws[t]) for t in TEAM_SHORT]
    all_t.sort(key=lambda x: (-x[1], x[2]))
    lw, ll = all_t[0][1], all_t[0][2]

    standings = []
    for rank, (team, w, l, d) in enumerate(all_t, 1):
        tot = w + l + d
        pct = f'.{round(w/tot*1000):03d}' if tot else '.000'
        gb  = '-' if rank == 1 else str(round(((lw-w)+(l-ll))/2, 1))
        last = last5[team][-5:]
        if last:
            cur = last[-1]
            cnt = sum(1 for x in reversed(last) if x == cur)
            streak = f"{cur}{cnt}"
        else:
            streak = ''
        standings.append({'rank':rank,'team':team,'win':w,'loss':l,'draw':d,
                          'pct':pct,'gb':gb,'streak':streak})
    return standings

# ── 演唱會（tickettw.com）────────────────────────────────

def fetch_concerts():
    """
    抓 tickettw 新資料，與現有 concerts.json 合併：
    - 現有資料保留（不蓋掉手動加的場次）
    - tickettw 有的自動更新售票狀態
    - tickettw 新出現的自動新增
    """
    # 讀取現有資料
    existing = {}
    old_data = load_json('data/concerts.json')
    if old_data:
        for c in old_data.get('concerts', []):
            existing[c['title']] = c

    # 從 tickettw 抓新資料
    scraped = {}
    for page in range(1, 11):
        url = f'https://www.tickettw.com/concerts?page={page}'
        try:
            soup = fetch_soup(url)
        except Exception as e:
            print(f"  ⚠️ tickettw 第{page}頁失敗: {e}")
            break

        links = soup.select('a[href*="/concert-ticket/"]')
        if not links:
            break

        page_has_future = False

        for link in links:
            href  = 'https://www.tickettw.com' + link['href']
            block = link.get_text(' ', strip=True)

            # 標題
            title = re.split(r'演出日期', block)[0]
            title = re.sub(r'\s*圖片\s*', '', title).strip()
            title = re.split(r'[｜|]', title)[0].strip()
            half = len(title) // 2
            if half > 0 and title[:half].strip() == title[half:].strip():
                title = title[:half].strip()
            if not title:
                continue

            # 演出日期
            date_m = re.search(r'演出日期[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日)', block)
            if not date_m:
                continue
            date_str = parse_tw_date(date_m.group(1))
            if not date_str or not is_future(date_str):
                continue

            # 演出場館
            venue_m = re.search(r'演出場館[:：]\s*([\S ]+?)(?:門票|全面|優先|⏰|🔔|\n|$)', block)
            venue = venue_m.group(1).strip() if venue_m else ''
            if not any(kw in venue for kw in TARGET_VENUES):
                continue

            page_has_future = True

            # 售票狀態
            sale_m = re.search(r'全面開賣[:：]\s*([\S ]+?)(?:優先|⏰|🔔|\n|$)', block)
            sale_raw = (sale_m.group(1).strip() if sale_m else '').split('  ')[0]
            sold_out = '已完售' in block
            if sold_out:
                sale_date = '已完售'
            elif '有待公佈' in sale_raw or not sale_raw:
                sale_date = '待公布'
            else:
                sd_m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', sale_raw)
                if sd_m:
                    sale_date = parse_tw_date(sd_m.group(1))
                    plat_m = re.search(r'(KKTIX|TIXCRAFT|TICKET PLUS|IBON|寬宏|年代|friDay|Weverse)', sale_raw, re.I)
                    if plat_m: sale_date += f' {plat_m.group(1).upper()}'
                else:
                    sale_date = '已開賣'

            plat_all = re.findall(r'(KKTIX|TIXCRAFT|TICKET PLUS|IBON|寬宏|年代|friDay|Weverse)', block, re.I)
            platform = plat_all[-1].upper() if plat_all else 'tickettw'

            scraped[title] = {
                'title': title, 'date': date_str,
                'venue': norm_venue(venue),
                'sale_date': sale_date, 'sold_out': sold_out,
                'url': href, 'platform': platform,
            }

        if not page_has_future:
            break

    print(f"  → tickettw 抓到 {len(scraped)} 筆大型場館場次")

    # 合併：tickettw 有的更新售票狀態；沒有的保留現有
    merged = dict(existing)  # 先複製現有

    new_count, update_count = 0, 0
    for title, item in scraped.items():
        if title in merged:
            # 更新售票日期和售完狀態，其他欄位保留
            merged[title]['sale_date'] = item['sale_date']
            merged[title]['sold_out']  = item['sold_out']
            update_count += 1
        else:
            merged[title] = item
            new_count += 1

    print(f"  → 新增 {new_count} 筆，更新 {update_count} 筆，保留 {len(merged)-new_count-update_count} 筆")

    # 只保留未來場次，依日期排序
    result = [c for c in merged.values() if is_future(c['date'])]
    result.sort(key=lambda x: x['date'])
    print(f"  → 演唱會共 {len(result)} 筆")
    return result if result else None

# ── 主程式 ────────────────────────────────────────────────

def main():
    print("🔄 開始抓取資料...")
    now = datetime.now().isoformat()

    print("\n📅 CPBL 賽程...")
    games_future, games_past = fetch_cpbl()

    print("\n🏆 計算積分榜...")
    # 優先用解析到的過去比賽；若太少再從文字掃描
    if len(games_past) < 5:
        print("  → 過去比賽太少，改用文字掃描...")
        game_results = fetch_scores_for_standings()
    else:
        game_results = games_past

    standings = calc_standings(game_results)
    total_wl = sum(t['win']+t['loss'] for t in standings)
    if total_wl == 0:
        print("  ⚠️ 積分榜勝負均為 0（比分未抓到），保留舊資料")
        standings = None

    recent = sorted(game_results, key=lambda x: x.get('date',''), reverse=True)[:15]
    recent = [{'date':g['date'],'away':g['away'],'away_score':g.get('away_score',0),
               'home':g['home'],'home_score':g.get('home_score',0)} for g in recent]

    print("\n🎤 演唱會（tickettw）...")
    concerts = fetch_concerts()

    # 儲存
    save('data/cpbl.json', {'updated': now, 'games': games_future})

    if standings:
        save('data/standings.json', {'updated': now, 'standings': standings, 'recent': recent})
        print(f"  → 積分榜 {len(standings)} 隊")
    else:
        old = load_json('data/standings.json') or {}
        old.update({'updated': now})
        if recent: old['recent'] = recent
        save('data/standings.json', old)

    if concerts:
        save('data/concerts.json', {'updated': now, 'concerts': concerts})
    else:
        print("  ⚠️ 演唱會合併結果為空，保留現有資料")

    print(f"\n✅ 完成！未來賽程 {len(games_future)} 場，"
          f"積分榜 {'OK' if standings else '保留舊'} ，"
          f"演唱會 {len(concerts) if concerts else '保留舊'} 筆")

if __name__ == '__main__':
    main()
