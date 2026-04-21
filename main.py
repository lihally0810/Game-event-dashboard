import pandas as pd
import os
import json
import traceback
import re
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

# 설정
EXCEL_FILE = "events.xlsx"
CSS_FILE = "style.css"
HISTORY_FILE = "history.json"

def resource_path(relative_path):
    """ 실행 파일 내에 포함된 리소스의 실제 경로를 반환합니다. """
    try:
        import sys
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_weekday_ko(dt):
    """datetime 객체에서 한국어 요일을 반환합니다."""
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return weekdays[dt.weekday()]

def parse_date_smart(date_str):
    """다양한 형식의 날짜 문자열을 인식하여 datetime 객체로 반환합니다."""
    if not date_str or str(date_str).lower() in ['nan', 'none', '', 'null']:
        return None
    
    try:
        # 숫자 추출 (연, 월, 일, 시, 분)
        nums = re.findall(r'\d+', str(date_str))
        
        if len(nums) >= 2:
            now = datetime.now()
            # 연도 판별: 4자리 숫자가 있으면 연도로 사용, 없으면 현재 연도 사용
            year = now.year
            month, day = 1, 1
            hour, minute = 23, 59
            
            idx = 0
            if len(nums[0]) == 4:
                year = int(nums[0])
                idx = 1
            
            if len(nums) > idx + 1:
                month = int(nums[idx])
                day = int(nums[idx+1])
                if len(nums) > idx + 2:
                    hour = int(nums[idx+2])
                if len(nums) > idx + 3:
                    minute = int(nums[idx+3])
            
            return datetime(year, month, day, hour, minute)
    except:
        return None
    return None

def normalize_period(period_str):
    """기간 문자열을 'MM.DD(요일) HH:MM ~ MM.DD(요일) HH:MM' 형식으로 통합합니다."""
    if not period_str or str(period_str).lower() in ['nan', 'none', '', 'null']:
        return "기간 정보 없음"
    
    # '~' 또는 '-' 로 구분 시도
    parts = re.split(r'[~-]', str(period_str))
    
    normalized_parts = []
    for part in parts:
        part = part.strip()
        dt = parse_date_smart(part)
        if dt:
            # 포맷: MM.DD(요일) HH:MM
            normalized_parts.append(f"{dt.month:02d}.{dt.day:02d}({get_weekday_ko(dt)}) {dt.hour:02d}:{dt.minute:02d}")
        else:
            # 날짜 형식이 아니면 (예: '업데이트 후', '상시') 원본 유지
            normalized_parts.append(part)
    
    return " ~ ".join(normalized_parts)

def load_events_from_excel(file_path):
    """Excel 파일에서 데이터를 읽고 날짜를 정규화합니다. (저장 기능 없음)"""
    if not os.path.exists(file_path):
        print(f"[Error] {file_path} 파일이 존재하지 않습니다.")
        return []

    try:
        df = pd.read_excel(file_path)
        events = []
        now = datetime.now()
        
        # 이전 데이터 로드 (NEW 배지 판정용)
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except: pass
        
        # 비교를 위한 키 세트 생성 (게임, 카테고리, 제목)
        history_keys = {f"{h.get('game')}|{h.get('category')}|{h.get('title')}" for h in history}
        
        for _, row in df.iterrows():
            game = str(row.get('게임', '기타')).strip()
            category = str(row.get('카테고리', '인 게임')).strip()
            title = str(row.get('제목', '제목 없음')).strip()
            period_raw = str(row.get('기간', '기간 정보 없음')).strip()
            lounge_link = str(row.get('공지링크', '#')).strip()
            web_link = str(row.get('이벤트링크', 'null')).strip()
            
            # 날짜 정규화
            period = normalize_period(period_raw)
            
            # 마감 임박 자동 판정 (종료일 추출 시도)
            excel_urgent = str(row.get('마감임박', 'FALSE')).upper() == 'TRUE'
            urgent_tag_text = ""
            
            # 기간 문자열에서 마지막 날짜 추출
            parts = re.split(r'[~-]', period_raw)
            if len(parts) >= 2:
                end_date = parse_date_smart(parts[-1].strip())
                if end_date:
                    # 날짜 차이 계산 (시간 제외하고 날짜로만 비교)
                    today_date = now.date()
                    end_date_only = end_date.date()
                    diff_days = (end_date_only - today_date).days
                    
                    if diff_days == 0:
                        urgent_tag_text = "D-Day"
                    elif 0 < diff_days <= 3:
                        urgent_tag_text = f"D-{diff_days}"
            
            # 엑셀에서 수동으로 마감임박을 TRUE로 한 경우 처리 (날짜 정보가 없을 때 대비)
            if excel_urgent and not urgent_tag_text:
                urgent_tag_text = "마감임박"
            
            if web_link.lower() in ['nan', 'none', '', 'null']:
                web_link = None
            
            # NEW 배지 판정: 이전 기록에 없으면 True
            current_key = f"{game}|{category}|{title}"
            is_new = current_key not in history_keys
            
            events.append({
                "game": game,
                "category": category,
                "title": title,
                "period": period,
                "lounge_link": lounge_link,
                "web_link": web_link,
                "urgent_tag": urgent_tag_text,
                "is_new": is_new
            })
        
        print(f"[System] 데이터 로드 및 정규화 완료: {len(events)}개 항목 (새 항목: {sum(1 for e in events if e['is_new'])}개)")
        
        # 현재 상태를 히스토리에 저장 (다음 실행 시 NEW 제거를 위해)
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
        except: pass
        
        return events
    except Exception:
        print("[Error] Excel 파일을 읽는 중 오류가 발생했습니다.")
        traceback.print_exc()
        return []

def generate_html(events):
    """정규화된 데이터를 기반으로 대시보드 생성"""
    if not events:
        print("[Warning] 수집된 이벤트 데이터가 없습니다. index.html 업데이트를 중단합니다.")
        return
    
    css_content = ""
    # 1. 외부 style.css 확인 (사용자 수정 가능성)
    # 2. EXE 내부 번들된 style.css 확인
    try:
        if os.path.exists(CSS_FILE):
            with open(CSS_FILE, "r", encoding="utf-8") as f:
                css_content = f.read()
        else:
            bundled_css = resource_path(CSS_FILE)
            if os.path.exists(bundled_css):
                with open(bundled_css, "r", encoding="utf-8") as f:
                    css_content = f.read()
            else:
                print(f"[Warning] {CSS_FILE} 파일을 찾을 수 없습니다.")
    except: pass

    grouped = {}
    available_games = []
    
    for ev in events:
        g = ev.get("game", "기타")
        c = ev.get("category", "인 게임")
        if g not in grouped: 
            grouped[g] = {}
            available_games.append(g)
        if c not in grouped[g]: 
            grouped[g][c] = []
        grouped[g][c].append(ev)

    sidebar_html = ""
    main_html = ""
    
    for i, game_name in enumerate(available_games):
        active_cls = "active" if i == 0 else ""
        game_id = f"game_{i}"
        sidebar_html += f'<button class="sidebar-item {active_cls}" onclick="switchGame(\'{game_id}\', this)">{game_name}</button>'
        
        game_events = grouped.get(game_name, {})
        section_content = f'<div class="header-group"><h2 class="section-game-title">{game_name}</h2><span class="live-indicator">LIVE</span></div>'
        
        kanban_grid = ""
        categories = ['인 게임', '쿠폰', '커뮤니티', '오프라인']
        for cat in game_events.keys():
            if cat not in categories:
                categories.append(cat)
                
        for category in categories:
            ev_list = game_events.get(category, [])
            if not ev_list and category != '인 게임': continue
            
            cards = ""
            for ev in ev_list:
                tag_text = ev.get("urgent_tag", "")
                urgent_tag = f'<span class="tag-urgent">{tag_text}</span>' if tag_text else ""
                
                # NEW 배지 추가
                new_tag = '<span class="tag-new">NEW</span>' if ev.get("is_new") else ""
                
                if category == "쿠폰":
                    origin_title = ev.get('title', '제목없음')
                    codes = [c.strip() for c in origin_title.split('/')]
                    title_html = '<div class="coupon-group">'
                    for code in codes:
                        title_html += f'<span class="coupon-code" onclick="copyToClipboard(\'{code}\', this)">{code} <i class="far fa-copy"></i></span>'
                    title_html += '</div>'
                    # 쿠폰은 공지 버튼 생략
                    lounge_btn = ""
                else:
                    title_html = f'<div class="card-title">{ev.get("title", "제목없음")}</div>'
                    lounge_btn = f'<a href="{ev.get("lounge_link", "#")}" target="_blank" class="btn-lounge">공지 확인</a>'

                web_btn = f'<a href="{ev.get("web_link")}" target="_blank" class="btn-web">참여 페이지</a>' if ev.get("web_link") else ""
                cards += f"""
                <div class="event-card">
                    <div class="card-header">{urgent_tag}{new_tag}</div>
                    <div class="card-body">
                        {title_html}
                        <div class="card-period"><i class="far fa-clock"></i> {ev.get('period', '기간 확인 중')}</div>
                    </div>
                    <div class="card-footer">
                        {lounge_btn}
                        {web_btn}
                    </div>
                </div>
                """
            kanban_grid += f"""
            <div class="kanban-column">
                <h3 class="column-title">{category} <span class="count">{len(ev_list)}</span></h3>
                <div class="column-grid">{cards}</div>
            </div>
            """
        section_content += f'<div class="kanban-layout">{kanban_grid}</div>'
        
        display_style = "display: block;" if i == 0 else "display: none;"
        main_html += f'<div id="{game_id}" class="game-content" style="{display_style}">{section_content}</div>'

    html_template = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Game Event Dashboard</title>
    <style>{css_content}</style>
    <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="app-layout">
        <aside class="sidebar">
            <div class="sidebar-header">
                <div class="logo">
                     <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M12 2L2 7V17L12 22L22 17V7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <span>EVENT TRACKER</span>
                </div>
            </div>
            <nav class="sidebar-nav">{sidebar_html}</nav>
            <div class="sidebar-footer">
                <div class="update-info">
                    <div class="status-dot"></div>
                    <span>동기화 완료: {datetime.now().strftime('%m/%d %H:%M')}</span>
                </div>
            </div>
        </aside>
        <main class="main-container">
            <div class="container-inner">
                {main_html}
            </div>
        </main>
    </div>
    <div id="toast" class="toast">복사 완료! 🎁</div>
    <script>
        function copyToClipboard(text, el) {{
            navigator.clipboard.writeText(text).then(() => {{
                const toast = document.getElementById('toast');
                toast.classList.add('show');
                const originalContent = el.innerHTML;
                el.innerHTML = 'COPIED! <i class="fas fa-check"></i>';
                el.classList.add('copied');
                setTimeout(() => {{
                    toast.classList.remove('show');
                    el.innerHTML = originalContent;
                    el.classList.remove('copied');
                }}, 1500);
            }});
        }}
        function switchGame(gameId, btn) {{
            document.querySelectorAll('.game-content').forEach(el => {{
                el.style.opacity = '0';
                setTimeout(() => el.style.display = 'none', 200);
            }});
            document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
            setTimeout(() => {{
                const target = document.getElementById(gameId);
                if (target) {{
                    target.style.display = 'block';
                    setTimeout(() => target.style.opacity = '1', 50);
                }}
            }}, 200);
            btn.classList.add('active');
        }}
    </script>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)
    print("[Success] index.html 최종 업데이트 완료.")

def send_discord_notification(events, webhook_url):
    """마감 임박 이벤트를 추려 디스코드 웹후크로 알림을 보냅니다."""
    now = datetime.now()
    urgent_events = [ev for ev in events if ev.get("urgent_tag") and "D-" in ev.get("urgent_tag") or ev.get("urgent_tag") == "D-Day"]
    
    if not urgent_events:
        print("[System] 마감 임박 이벤트가 없어 디스코드 알림을 건너뜁니다.")
        return

    # 게임별로 그룹화
    game_groups = {}
    for ev in urgent_events:
        game = ev['game']
        if game not in game_groups: game_groups[game] = []
        game_groups[game].append(ev)

    embeds = []
    for game, ev_list in game_groups.items():
        description = ""
        for ev in ev_list:
            tag = f"**[{ev['urgent_tag']}]**"
            category = f"`{ev['category']}`"
            description += f"{tag} {category} {ev['title']}\n"
            description += f"└ 🕒 {ev['period']}\n\n"
        
        embeds.append({
            "title": f"🎮 {game} 마감 임박 이벤트",
            "description": description,
            "color": 15814466, # Urgent Red
            "footer": {"text": "Game Event Tracker | " + now.strftime('%Y-%m-%d %H:%M')}
        })

    # 전체 대시보드 링크 추가
    dashboard_url = "https://lihally0810.github.io/Game-event-dashboard/"
    
    payload = {
        "content": f"📢 **오늘의 게임 이벤트 마감 현황입니다!**\n자세한 내용은 [대시보드]({dashboard_url})에서 확인하세요.",
        "embeds": embeds[:10] # 디스코드는 한 번에 최대 10개 임베드 가능
    }

    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 204:
            print("[Success] 디스코드 알림 전송 완료.")
        else:
            print(f"[Warning] 디스코드 알림 전송 실패: {response.status_code}")
    except Exception as e:
        print(f"[Error] 디스코드 알림 중 오류 발생: {e}")

if __name__ == "__main__":
    import sys
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print(f"[System] 대시보드 업데이트를 시작합니다...")
    event_data = load_events_from_excel(EXCEL_FILE)
    generate_html(event_data)

    # 디스코드 알림 전송
    load_dotenv()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        send_discord_notification(event_data, webhook_url)
    else:
        print("[Warning] DISCORD_WEBHOOK_URL이 설정되지 않아 알림을 보낼 수 없습니다.")
