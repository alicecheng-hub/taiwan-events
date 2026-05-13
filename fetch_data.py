#!/usr/bin/env python3
"""
fetch_data.py
- 棒球賽程：解析 LINE TODAY 頁面 HTML（資料直接寫在頁面，非 JS 動態）
- 積分榜：解析 LINE TODAY 頁面 HTML
- 演唱會：解析 tickettw.com（只取大型場館）
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
TEAM_NORM = {'統一7-ELEVEn獅':'統一獅', '統一7-eleven獅':'統一獅'}

TARGET_VENUES = ['台北大巨蛋','大巨蛋','台北小巨蛋','小巨蛋',
                 '高雄巨蛋','高雄世運','高雄流行音樂','海音館',
                 '台中洲際','台中巨蛋']

# ── 工具 ──────────────────────────────────────────────────

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 儲存 {path}")

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')

def norm_team(n):
    for k,v in TEAM_NORM.items():
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

def parse_date_str(s, year=None):
    y = year or CUR_YEAR
    m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m: return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    m = re.search(r'(\d{1,2})[/-](\d{1,2})', s)
    if m: return f"{y}/{int(m.group(1)):02d}/{int(m.group(2)):02d}"
    return ''

def is_future_or_today(date_str):
    try:
        return datetime.strptime(date_str, '%Y/%m/%d').date() >= TODAY
    except: return False

# ── CPBL 賽程（LINE TODAY HTML 解析）────────────────────

def fetch_cpbl():
    """
    LINE TODAY 頁面的比賽資料直接寫在 HTML 裡，可用 BeautifulSoup 抓。
    結構：每場比賽是一個 <a> 連結，內含時間、場地、兩隊名稱。
    日期 header 在比賽 <a> 之前的 div/section 裡。
    """
    games = []
    url   = f'https://today.line.me/tw/v3/baseball/seasons/{SEASON}/schedule'
    try:
        soup = fetch(url)
        text = soup.get_text('\n')

        # 逐行解析：遇到 M/D 日期就更新 current_date；
        # 遇到時間就開始收一場比賽的資訊
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        current_date = ''
        i = 0
        while i < len(lines):
            line = lines[i]

            # 日期行：3/28 / 4/1 / 12/31 （只有月/日，無年份）
            if re.fullmatch(r'\d{1,2}/\d{1,2}', line):
                current_date = f"{CUR_YEAR}/{int(line.split('/')[0]):02d}/{int(line.split('/')[1]):02d}"
                i += 1
                continue

            # 時間行：18:05 / 18:35 / 14:05
            if re.fullmatch(r'\d{1,2}:\d{2}', line) and current_date:
                time_str = line
                # 往後找場地和球隊
                venue = ''
                found_teams = []
                j = i + 1
                while j < len(lines) and len(found_teams) < 2:
                    candidate = lines[j]
                    # 場地
                    if not venue and any(k in candidate for k in
                        ['巨蛋','洲際','澄清湖','亞太','桃園','新莊','天母','斗六','嘉義','世運']):
                        venue = candidate
                    # 球隊
                    for t in TEAMS:
                        if t in candidate and candidate not in [v for _,v,_ in [(None,None,None)]]:
                            found_teams.append(norm_team(t))
                            break
                    j += 1
                    if j - i > 12:  # 最多掃12行
                        break

                if len(found_teams) == 2 and current_date:
                    if is_future_or_today(current_date):
                        games.append({
                            'date':    current_date,
                            'time':    time_str,
                            'away':    found_teams[0],
                            'home':    found_teams[1],
                            'stadium': norm_venue(venue),
                        })
                i += 1
                continue

            i += 1

        # 去除重複（同場次可能被掃到多次）
        seen, out = set(), []
        for g in games:
            key = f"{g['date']}{g['time']}{g['away']}{g['home']}"
            if key not in seen:
                seen.add(key)
                out.append(g)

        print(f"  → 賽程 {len(out)} 場")
        return sorted(out, key=lambda x: (x['date'], x['time']))

    except Exception as e:
        print(f"⚠️ 賽程失敗: {e}")
        return []

# ── CPBL 積分榜（LINE TODAY HTML）───────────────────────

def fetch_standings():
    """
    嘗試解析 LINE TODAY 積分榜頁面。
    如果 404，改從文字內容裡的積分資料抓。
    """
    standings, recent = [], []

    # 先試 schedule 頁（頁面側邊欄可能有積分）或獨立積分頁
    for path in ['standing', 'standings', 'rank', 'leaderboard']:
        url = f'https://today.line.me/tw/v3/baseball/seasons/{SEASON}/{path}'
        try:
            soup = fetch(url)
            text = soup.get_text('\n')
            lines = [l.strip() for l in text.splitlines() if l.strip()]

            i = 0
            rank = 1
            while i < len(lines):
                line = lines[i]
                # 找球隊名稱
                team = None
                for t in TEAMS:
                    if t in line:
                        team = norm_team(t)
                        break
                if team:
                    # 往後找 W-L-D 數字
                    nums = []
                    for k in range(i+1, min(i+8, len(lines))):
                        if re.fullmatch(r'\d+', lines[k]):
                            nums.append(int(lines[k]))
                        if len(nums) >= 3:
                            break
                    if len(nums) >= 3:
                        w, l, d = nums[0], nums[1], nums[2]
                        tot = w + l + d
                        pct = f'.{round(w/tot*1000):03d}' if tot else '.000'
                        standings.append({'rank':rank,'team':team,
                                          'win':w,'loss':l,'draw':d,
                                          'pct':pct,'gb':'-','streak':''})
                        rank += 1
                i += 1

            if standings:
                print(f"  → 積分榜 {len(standings)} 隊（from {path}）")
                break
        except Exception as e:
            continue

    if not standings:
        print("⚠️ 積分榜所有路徑均失敗，保留現有資料")

    # 近期戰績：從 schedule 頁面裡已完成的比賽抓（有比分的）
    try:
        soup = fetch(f'https://today.line.me/tw/v3/baseball/seasons/{SEASON}/schedule')
        text = soup.get_text('\n')
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        cur_date = ''
        i = 0
        while i < len(lines) and len(recent) < 15:
            line = lines[i]
            if re.fullmatch(r'\d{1,2}/\d{1,2}', line):
                cur_date = f"{CUR_YEAR}/{int(line.split('/')[0]):02d}/{int(line.split('/')[1]):02d}"
            # 找「X:Y」比分（非時間格式，數字較小）
            score_m = re.fullmatch(r'(\d{1,2})', line)
            if score_m and cur_date and not is_future_or_today(cur_date):
                # 在附近找兩個分數和兩支球隊
                candidates = lines[max(0,i-5):i+5]
                teams_found = []
                scores_found = []
                for c in candidates:
                    for t in TEAMS:
                        if t in c and norm_team(t) not in teams_found:
                            teams_found.append(norm_team(t))
                    if re.fullmatch(r'\d{1,2}', c):
                        scores_found.append(int(c))
                if len(teams_found)==2 and len(scores_found)>=2:
                    key = f"{cur_date}{teams_found[0]}{teams_found[1]}"
                    if not any(r['date']==cur_date and r['away']==teams_found[0] for r in recent):
                        recent.append({'date':cur_date,
                                       'away':teams_found[0],'away_score':scores_found[0],
                                       'home':teams_found[1],'home_score':scores_found[1]})
            i += 1
        print(f"  → 近期戰績 {len(recent)} 場")
    except Exception as e:
        print(f"⚠️ 近期戰績失敗: {e}")

    return standings, recent

# ── 演唱會（tickettw.com）────────────────────────────────

def fetch_concerts():
    concerts = []
    seen = set()

    for page in range(1, 15):
        url = f'https://www.tickettw.com/concerts?page={page}'
        try:
            soup = fetch(url)
        except Exception as e:
            print(f"  ⚠️ tickettw 第{page}頁失敗: {e}")
            break

        # 嘗試各種可能的 card selector
        cards = (soup.select('[class*="ConcertItem"], [class*="concert-item"]') or
                 soup.select('[class*="EventCard"], [class*="event-card"]') or
                 soup.select('article') or
                 soup.select('[class*="card"]'))

        if not cards:
            print(f"  ⚠️ tickettw 第{page}頁找不到 card，停止")
            break

        page_has_future = False

        for card in cards:
            # 取文字
            full_text = card.get_text(' ', strip=True)

            # 標題
            title_el = (card.select_one('h2') or card.select_one('h3') or
                        card.select_one('[class*="title"]') or card.select_one('[class*="name"]'))
            title = title_el.get_text(strip=True) if title_el else ''
            if not title:
                # 用第一行非空文字當標題
                for line in full_text.split('  '):
                    if line.strip() and len(line.strip()) > 3:
                        title = line.strip()[:80]
                        break
            if not title or title in seen:
                continue

            # 日期
            date_raw = ''
            date_el = card.select_one('[class*="date"], time, [class*="time"]')
            if date_el:
                date_raw = date_el.get_text(strip=True)
            else:
                # 從全文抓第一個日期
                dm = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', full_text)
                if dm:
                    date_raw = dm.group(0)

            date_str = parse_date_str(date_raw)
            if not date_str or not is_future_or_today(date_str):
                continue

            # 場館
            venue_el = card.select_one('[class*="venue"], [class*="location"], [class*="place"]')
            venue = venue_el.get_text(strip=True) if venue_el else ''
            if not venue:
                # 從全文找場館關鍵字
                for kw in ['大巨蛋','小巨蛋','高雄巨蛋','世運','海音館','台中洲際','台中巨蛋']:
                    if kw in full_text:
                        venue = kw
                        break

            if not any(kw in venue for kw in TARGET_VENUES):
                continue

            page_has_future = True

            # 售票狀態
            sold_out = bool(card.select_one('[class*="sold-out"], [class*="soldout"]'))
            sale_el  = card.select_one('[class*="sale"], [class*="ticket-date"], [class*="open"]')
            sale_raw = sale_el.get_text(strip=True) if sale_el else ''

            if sold_out:
                sale_date = '已完售'
            elif '已開賣' in sale_raw or '售票中' in full_text:
                sale_date = '已開賣'
            elif sale_raw:
                dm2 = re.search(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', sale_raw)
                sale_date = dm2.group(0).replace('-','/') if dm2 else sale_raw[:30]
            else:
                # 從全文找售票日期
                dm3 = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2}).{0,5}(開賣|售票)', full_text)
                if dm3:
                    sale_date = f"{dm3.group(1)}/{int(dm3.group(2)):02d}/{int(dm3.group(3)):02d} 開賣"
                elif '待公布' in full_text or '尚未' in full_text:
                    sale_date = '待公布'
                else:
                    sale_date = '已開賣'

            # 連結
            link_el = card.select_one('a[href]')
            href = link_el['href'] if link_el else ''
            if href and not href.startswith('http'):
                href = 'https://www.tickettw.com' + href

            seen.add(title)
            concerts.append({
                'title':    title,
                'date':     date_str,
                'venue':    norm_venue(venue),
                'sale_date': sale_date,
                'sold_out': sold_out,
                'url':      href,
                'platform': 'tickettw',
            })

        if not page_has_future:
            print(f"  → 第{page}頁無未來場次，停止翻頁")
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

    print("\n🎤 演唱會...")
    concerts = fetch_concerts()

    save('data/cpbl.json', {'updated': now, 'games': cpbl})

    if standings:
        save('data/standings.json', {'updated': now, 'standings': standings, 'recent': recent})
    else:
        # 積分榜抓不到時只更新 recent，不動 standings
        try:
            with open('data/standings.json', 'r', encoding='utf-8') as f:
                old = json.load(f)
            old['recent'] = recent
            old['updated'] = now
            save('data/standings.json', old)
            print("  → 積分榜保留舊資料，只更新近期戰績")
        except:
            save('data/standings.json', {'updated': now, 'standings': [], 'recent': recent})

    if concerts:
        save('data/concerts.json', {'updated': now, 'concerts': concerts})
    else:
        print("  → 演唱會保留現有資料")

    print(f"\n✅ 完成！賽程 {len(cpbl)} 場，積分榜 {len(standings)} 隊，演唱會 {len(concerts) if concerts else '保留舊'} 筆")

if __name__ == '__main__':
    main()
