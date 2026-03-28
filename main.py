import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# 환경 변수 및 설정
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
LOUNGES = {
    "WutheringWaves": {
        "name": "명조: 워더링 웨이브",
        "boards": [
            {"id": "3", "category": "커뮤니티/오프라인"},
            {"id": "28", "category": "인 게임"}
        ]
    },
    "ZZZ": {
        "name": "젠레스 존 제로",
        "boards": [
            {"id": "13", "category": "커뮤니티/오프라인"},
            {"id": "11", "category": "인 게임"}
        ]
    },
    "Trickcal": {
        "name": "트릭컬: 리바이브",
        "boards": [
            {"id": "13", "category": "전체 이벤트"}
        ]
    }
}

def get_full_text(url):
    """게시글 상세 페이지 방문하여 본문 전체 텍스트 수집 (정확도 1순위 전술)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 네이버 라운지 본문 전용 셀렉터
        content_area = soup.select_one(".se-viewer") or soup.select_one("div[class^='detail_contents']")
        if content_area:
            return content_area.get_text("\n", strip=True)
        return ""
    except Exception as e:
        print(f"⚠️ 본문 수집 실패 ({url}): {e}")
        return ""

def collect_game_data(lounge_id, info):
    """각 게임별로 15개의 최신글에 대해 본문 전체를 딥 스크래핑합니다."""
    all_game_feeds = []
    for board in info["boards"]:
        board_id = board["id"]
        url = f"https://game-api.naver.com/game/v1/lounge/{lounge_id}/feed?boardId={board_id}&page=1&pageSize=15"
        try:
            res = requests.get(url, timeout=10)
            data = res.json()
            if data.get("code") == 200:
                feeds = data["contents"]["feeds"]
                for f in feeds:
                    link = f"https://game.naver.com/lounge/{lounge_id}/board/detail/{f['feed']['feedId']}"
                    print(f"🔎 {info['name']} 정밀 스캔 중: {f['feed']['title'][:20]}...")
                    full_text = get_full_text(link)
                    
                    all_game_feeds.append({
                        "game": info["name"],
                        "title": f['feed']['title'],
                        "link": link,
                        "full_text": full_text
                    })
        except Exception as e:
            print(f"❌ {info['name']} 게시판({board_id}) 수집 오류: {e}")
    return all_game_feeds

def analyze_game_events(game_name, raw_data):
    """게임별 분할 분석을 통해 AI의 집중도와 정확도를 극대화합니다."""
    if not model or not raw_data:
        return []

    prompt = f"""
너는 게임 데이터 분석 전문가야. 제공된 '{game_name}'의 전체 본문 데이터를 기반으로 현재 진행 중인 한정 이벤트 정보를 JSON 배열로 반환해.

### 데이터 (본문 전체):
{json.dumps(raw_data, ensure_ascii=False)}

### 🔍 초정밀 추출 규칙 (사용자 피드백 반영):
1. **오늘 날짜**: {datetime.now().strftime('%Y-%m-%d')}
2. **카테고리 분류**: '커뮤니티', '오프라인', '인 게임' 중 하나로 분류.
   - **캐릭터/무기 모집(뽑기, 튜닝), 버전 소식, 인게임 미니게임/퍼즐**은 반드시 **'인 게임'**으로 분류.
3. **날짜 강제 추출 (1순위 명령)**: 
   - '진행 중' 또는 '상시', '정보 없음' 표현 사용 절대 금지.
   - 본문의 `일시`, `공간`, `~`, `/`, `AM/PM` 등을 샅샅이 뒤져 **정확한 시작일/종료일과 시각**을 찾아낼 것.
   - 형식: "3월 29일 11:00 ~ 4월 17일 03:59" (반드시 이 형식을 지킬 것)
4. **포함/제외**: 기간 한정 이벤트, 캐릭터 모집은 포함하고 단순 출석/접속 보상은 제외. 이미 종료된 이벤트는 무조건 삭제.
5. **상태**: 오늘 기준 종료까지 3일 이내 마감이면 `is_urgent: true`.

### ✍️ 출력 형식 (반드시 유효한 JSON 배열만 출력):
[
  {{
    "game": "{game_name}",
    "category": "커뮤니티/오프라인/인 게임",
    "title": "이벤트 명",
    "period": "X월 X일 00:00 ~ X월 X일 00:00",
    "lounge_link": "원본 게시글 링크",
    "web_link": "이벤트 참여 링크(없으면 null)",
    "is_urgent": true/false
  }}
]
"""
    try:
        response = model.generate_content(prompt)
        res_text = response.text.strip()
        if "```" in res_text:
            res_text = res_text.split("```")[1].replace("json", "").strip()
        
        events = json.loads(res_text)
        print(f"🤖 {game_name} 분석 완료: {len(events)}개 추출")
        return events
    except Exception as e:
        print(f"❌ {game_name} AI 분석 오류: {e}")
        return []

def generate_html(events):
    css_content = ""
    try:
        with open("style.css", "r", encoding="utf-8") as f:
            css_content = f.read()
    except:
        css_content = "/* CSS missing */"

    grouped = {}
    for ev in events:
        g = ev.get("game", "기타")
        c = ev.get("category", "기타")
        if g not in grouped: grouped[g] = {}
        if c not in grouped[g]: grouped[g][c] = []
        grouped[g][c].append(ev)

    sidebar_html = ""
    main_html = ""
    for i, (lounge_key, info) in enumerate(LOUNGES.items()):
        game_name = info["name"]
        active_cls = "active" if i == 0 else ""
        sidebar_html += f'<button class="sidebar-item {active_cls}" onclick="switchGame(\'{lounge_key}\', this)">{game_name}</button>'
        
        game_events = grouped.get(game_name, {})
        section_content = f'<h2 class="section-game-title">{game_name}</h2>'
        
        if not game_events:
            section_content += '<div class="empty-state">현재 진행 중인 이벤트가 없습니다.</div>'
        else:
            kanban_grid = ""
            for category in ['인 게임', '커뮤니티', '오프라인']:
                ev_list = game_events.get(category, [])
                if not ev_list and category != '인 게임': continue
                
                cards = ""
                for ev in ev_list:
                    urgent_tag = '<span class="tag-urgent">마감 임박</span>' if ev.get("is_urgent") else ""
                    web_btn = f'<a href="{ev["web_link"]}" target="_blank" class="btn btn-web">참여 페이지</a>' if ev.get("web_link") else ""
                    cards += f"""
                    <div class="event-card">
                        <div class="card-header">{urgent_tag}</div>
                        <div class="card-title">{ev['title']}</div>
                        <div class="card-period">{ev['period']}</div>
                        <div class="card-footer">
                            <a href="{ev['lounge_link']}" target="_blank" class="btn btn-lounge">공지 확인</a>
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
        main_html += f'<div id="{lounge_key}" class="game-content" style="{display_style}">{section_content}</div>'

    html_template = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Game Event Tracker</title>
    <style>{css_content}</style>
    <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body>
    <div class="app-layout">
        <aside class="sidebar">
            <div class="sidebar-header">EVENT TRACKER</div>
            <nav class="sidebar-nav">{sidebar_html}</nav>
            <div class="sidebar-footer">
                <div class="update-time">동기화 완료: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </aside>
        <main class="main-container">{main_html}</main>
    </div>
    <script>
        function switchGame(gameId, btn) {{
            document.querySelectorAll('.game-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
            document.getElementById(gameId).style.display = 'block';
            btn.classList.add('active');
        }}
    </script>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

if __name__ == "__main__":
    if not GOOGLE_API_KEY:
        print("❌ GOOGLE_API_KEY가 없습니다.")
        exit()

    genai.configure(api_key=GOOGLE_API_KEY)
    
    # 모델 선택 및 성능 테스트
    model = None
    for m_name in ['gemini-2.0-flash', 'gemini-pro-latest', 'gemini-flash-latest']:
        try:
            temp_model = genai.GenerativeModel(m_name)
            temp_model.generate_content("test", generation_config={"max_output_tokens": 1})
            model = temp_model
            print(f"🤖 {m_name} 초정밀 모델 연결 성공!")
            break
        except: continue

    final_all_events = []
    for lounge_id, info in LOUNGES.items():
        print(f"🚀 {info['name']} 정밀 수집 시작 (15개 분량)...")
        # 1. 게임별로 15개 본문 전체 스크래핑
        raw_data = collect_game_data(lounge_id, info)
        
        # 2. 게임별로 분할 분석하여 AI의 실수를 원천 봉쇄
        events = analyze_game_events(info['name'], raw_data)
        final_all_events.extend(events)

    print(f"📦 총 {len(final_all_events)}개의 이벤트를 HTML로 구성 중입니다...")
    generate_html(final_all_events)
    print("✨ 모든 초정밀 데이터 정화 작업이 끝났습니다!")
