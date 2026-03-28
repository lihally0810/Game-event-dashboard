import os
import json
import requests
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

# .env 파일 로드 (로컬 테스트용)
load_dotenv()

# 설정값
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    print("✅ GOOGLE_API_KEY를 찾았습니다.")
else:
    print("⚠️ GOOGLE_API_KEY가 설정되지 않았습니다. AI 분석이 불가능합니다.")

# 게임별 라운지 및 게시판 정보 (사용자 지정 업데이트)
LOUNGES = {
    "WutheringWaves": {"name": "명조: 워더링 웨이브", "boards": [3, 28]},
    "ZZZ": {"name": "젠레스 존 제로", "boards": [13, 11]},
    "Trickcal": {"name": "트릭컬: 리바이브", "boards": [13]}
}

def get_feeds(lounge_id, board_id):
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/{lounge_id}/feed?boardId={board_id}&buffFilteringYN=N&limit=10&offset=0&order=NEW"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("code") == 200:
            return data["content"]["feeds"]
    except Exception as e:
        print(f"Error fetching feeds for {lounge_id} (Board {board_id}): {e}")
    return []

def collect_all_data():
    collection = []
    for lounge_id, info in LOUNGES.items():
        game_feeds = []
        for board_id in info["boards"]:
            feeds = get_feeds(lounge_id, board_id)
            for feed in feeds:
                feed_data = {
                    "game": info["name"],
                    "title": feed["feed"]["title"],
                    "link": f"https://game.naver.com/lounge/{lounge_id}/board/detail/{feed['feed']['feedId']}",
                    "content_preview": feed["feed"].get("contents", "")[:1500]
                }
                game_feeds.append(feed_data)
        print(f"📡 {info['name']}에서 {len(game_feeds)}개의 소식을 가져왔습니다.")
        collection.append({"game": info["name"], "feeds": game_feeds})
    print(f"📊 총 {sum(len(c['feeds']) for c in collection)}개의 데이터를 수집했습니다.")
    return collection

def get_events_json(raw_data):
    if not GOOGLE_API_KEY:
        print("⚠️ GOOGLE_API_KEY가 없습니다.")
        return []

    genai.configure(api_key=GOOGLE_API_KEY)
    
    # 가용 가능한 모델 후보군 (사용자 환경 리스트 기반으로 재구성)
    model_candidates = ['gemini-pro-latest', 'gemini-flash-latest', 'gemini-2.0-flash']
    model = None
    
    for model_name in model_candidates:
        try:
            print(f"🤖 {model_name} 모델로 분석 시도 중...")
            temp_model = genai.GenerativeModel(model_name)
            # 모델이 정말 작동하는지 가볍게 테스트 (에러 발생 시 즉시 감지)
            temp_model.generate_content("test", generation_config={"max_output_tokens": 1})
            model = temp_model
            print(f"✅ {model_name} 모델 연결 성공!")
            break 
        except Exception as e:
            print(f"⚠️ {model_name} 모델 사용 불가: {e}")
            continue
            
    if not model:
        print("❌ 어떤 AI 모델도 사용할 수 없습니다. API 키 또는 할당량을 확인해 주세요.")
        return []
    
    prompt = f"""
너는 게임 데이터 분석가야. 아래 제공된 네이버 게임 라운지 데이터를 분석해서 한정 이벤트 정보를 JSON 배열로 반환해줘.

### 데이터:
{json.dumps(raw_data, ensure_ascii=False)}

### 🔍 추출 및 필터링 규칙 (엄격 준수):
1. **오늘 날짜**: {datetime.now().strftime('%Y-%m-%d')}
2. **카테고리 분류**: '커뮤니티', '오프라인', '인 게임' 중 하나로 분류. 특히 **캐릭터/무기 모집(뽑기), 인게임 미니게임/퍼즐**은 무조건 **'인 게임'**으로 분류할 것.
3. **포함**: 기간 한정 이벤트, 웹 이벤트, 콜라보레이션, 캐릭터/무기 모집. 특히 명조의 경우 **'캐릭터/무기 이벤트 튜닝'** 소식은 반드시 포함할 것.
4. **제외**: 단순 접속/출석체크(로그인 보상), 상시/정규 이벤트, **이미 종료된 이벤트(종료일이 오늘보다 이전이면 무조건 삭제)**.
5. **날짜 형식**: 기간(`period`)은 본문에서 찾아 **'3월 29일 ~ 4월 15일'** 또는 **'3월 29일 (상시)'** 형식으로 작성할 것. '정보 없음' 대신 본문 내의 기간 관련 문구를 최대한 활용할 것.
6. **상태**: 오늘 기준 종료까지 3일 이내 마감이면 `is_urgent: true`.

### ✍️ 출력 형식 (반드시 유효한 JSON 배열만 출력):
[
  {{
    "game": "게임명",
    "category": "커뮤니티/오프라인/인 게임",
    "title": "이벤트 명",
    "period": "X월 X일 ~ X월 X일 (또는 상시)",
    "lounge_link": "원본 게시글 링크",
    "web_link": "이벤트 참여 링크(없으면 null)",
    "is_urgent": true/false
  }},
  ...
]
"""
    try:
        response = model.generate_content(prompt)
        res_text = response.text.strip()
        
        if res_text.startswith("```"):
            res_text = res_text.split("```")[1]
            if res_text.startswith("json"):
                res_text = res_text[4:]
        
        events_list = json.loads(res_text.strip())
        print(f"🤖 AI가 이벤트를 {len(events_list)}개 추출했습니다.")
        return events_list
    except Exception as e:
        print(f"❌ LLM 처리 중 오류: {e}")
        return []

def generate_html(events):
    css_content = ""
    try:
        with open("style.css", "r", encoding="utf-8") as f:
            css_content = f.read()
    except:
        css_content = "/* CSS missing */"

    # 데이터 그룹화: 게임 -> 카테고리
    grouped = {}
    for ev in events:
        g = ev.get("game", "기타")
        c = ev.get("category", "기타")
        if g not in grouped: grouped[g] = {}
        if c not in grouped[g]: grouped[g][c] = []
        grouped[g][c].append(ev)

    # 사이드바 아이템 및 메인 콘텐츠 생성
    sidebar_html = ""
    main_html = ""
    
    # 게임 순서 유지 (LOUNGES 순서대로)
    for i, (lounge_key, info) in enumerate(LOUNGES.items()):
        game_name = info["name"]
        active_cls = "active" if i == 0 else ""
        sidebar_html += f'<button class="sidebar-item {active_cls}" onclick="switchGame(\'{lounge_key}\', this)">{game_name}</button>'
        
        # 해당 게임의 이벤트 섹션
        display_style = "display: block;" if i == 0 else "display: none;"
        game_events = grouped.get(game_name, {})
        
        section_content = f'<h2 class="section-game-title">{game_name}</h2>'
        if not game_events:
            section_content += '<div class="empty-state">현재 진행 중인 이벤트가 없습니다.</div>'
        else:
            kanban_grid = ""
            for category in ['인 게임', '커뮤니티', '오프라인']:
                ev_list = game_events.get(category, [])
                if not ev_list and category != '인 게임': continue # 인 게임은 비어있어도 컬럼 권장 (원하면 변경 가능)
                
                cards = ""
                for ev in ev_list:
                    urgent_tag = '<span class="tag-urgent">마감 임박</span>' if ev.get("is_urgent") else ""
                    web_btn = f'<a href="{ev["web_link"]}" target="_blank" class="btn btn-web">참여 페이지</a>' if ev.get("web_link") else ""
                    cards += f"""
                    <div class="event-card">
                        <div class="card-header">
                            {urgent_tag}
                        </div>
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
        
        main_html += f'<div id="{lounge_key}" class="game-content" style="{display_style}">{section_content}</div>'

    html_template = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Game Event Schedule</title>
    <style>{css_content}</style>
    <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body>
    <div class="app-layout">
        <aside class="sidebar">
            <div class="sidebar-header">EVENT TRACKER</div>
            <nav class="sidebar-nav">
                {sidebar_html}
            </nav>
            <div class="sidebar-footer">
                <div class="update-time">동기화 완료: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </aside>
        
        <main class="main-container">
            {main_html}
        </main>
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
    print("✨ index.html 개편 완료!")

if __name__ == "__main__":
    print("🚀 데이터 수집 시작...")
    raw_data = collect_all_data()
    
    print("🤖 AI 분석 중 (JSON 변환)...")
    events = get_events_json(raw_data)
    
    print(f"📦 {{len(events)}}개의 이벤트를 처리 중입니다. HTML을 생성합니다...")
    generate_html(events)
