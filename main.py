import requests
from bs4 import BeautifulSoup
import json
import os
import time
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
    """게시글 상세 페이지 방문하여 본문 전체 텍스트 수집 (안전성 강화)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return ""
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 네이버 라운지 본문 전용 셀렉터
        content_area = soup.select_one(".se-viewer") or soup.select_one("div[class^='detail_contents']")
        if content_area:
            return content_area.get_text("\n", strip=True)
        return ""
    except Exception as e:
        print(f"⚠️ 본문 수집 실패 안내 ({url}): {e}")
        return ""

def collect_game_data(lounge_id, info):
    """각 게임별로 15개의 최신글에 대해 본문 전체를 딥 스크래핑합니다 (딜레이 추가)"""
    all_game_feeds = []
    for board in info["boards"]:
        board_id = board["id"]
        url = f"https://game-api.naver.com/game/v1/lounge/{lounge_id}/feed?boardId={board_id}&page=1&pageSize=15"
        try:
            res = requests.get(url, timeout=12)
            if res.status_code != 200: continue
            data = res.json()
            feeds = data.get("contents", {}).get("feeds", [])
            for f in feeds:
                f_id = f.get('feed', {}).get('feedId')
                if not f_id: continue
                
                link = f"https://game.naver.com/lounge/{lounge_id}/board/detail/{f_id}"
                print(f"🔎 {info['name']} 정밀 스캔 중: {f['feed'].get('title', '제목없음')[:20]}...")
                full_text = get_full_text(link)
                
                all_game_feeds.append({
                    "game": info["name"],
                    "title": f['feed'].get('title', '제목없음'),
                    "link": link,
                    "full_text": full_text
                })
                time.sleep(0.3) # 네이버 서버 부하 방지 및 차단 회피
        except Exception as e:
            print(f"❌ {info['name']} 게시판({board_id}) 수집 오류: {e}")
    return all_game_feeds

def analyze_game_events(game_name, raw_data, ai_model):
    """게임별 분할 분석 (안전성 및 정확도 극대화)"""
    if not ai_model or not raw_data:
        return []

    prompt = f"""
너는 게임 데이터 분석 전문가야. 제공된 '{game_name}'의 전체 본문 데이터를 기반으로 현재 진행 중인 한정 이벤트 정보를 JSON 배열로 반환해.

### 데이터 (본문 전체):
{json.dumps(raw_data, ensure_ascii=False)}

### 🔍 초정밀 추출 규칙:
1. **오늘 날짜**: {datetime.now().strftime('%Y-%m-%d')}
2. **카테고리 분류**: '커뮤니티', '오프라인', '인 게임' 중 하나로 분류.
   - **캐릭터/무기 모집(뽑기, 튜닝), 버전 소식, 인게임 미니게임/퍼즐**은 반드시 **'인 게임'**으로 분류.
3. **날짜 강제 추출 (핵심)**: 
   - '진행 중' 또는 '상시', '정보 없음' 표현 사용 절대 금지.
   - 본문의 `일시`, `공간`, `~`, `/`, `AM/PM` 등을 샅샅이 뒤져 **정확한 시작일/종료일과 시각**을 찾아낼 것.
   - 형식: "3월 29일 11:00 ~ 4월 17일 03:59"
4. **포함/제외**: 기간 한정 이벤트, 캐릭터 모집은 포함하고 단순 출석 보상은 제외. 이미 종료된 이벤트는 무조건 삭제.
5. **상태**: 오늘 기준 종료까지 3일 이내 마감이면 `is_urgent: true`.

### ✍️ 출력 형식 (유효한 JSON 배열만 출력):
[
  {{
    "game": "{game_name}",
    "category": "... (분류)",
    "title": "... (이름)",
    "period": "X월 X일 00:00 ~ X월 X일 00:00",
    "lounge_link": "URL",
    "web_link": "URL(또는 null)",
    "is_urgent": true/false
  }}
]
"""
    try:
        response = ai_model.generate_content(prompt)
        res_text = response.text.strip()
        
        # JSON 정제 로직 강화
        if "```" in res_text:
            res_text = res_text.split("```")[1]
            if res_text.lower().startswith("json"):
                res_text = res_text[4:]
        
        res_text = res_text.strip()
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
                        <div class="card-title">{ev.get('title', '제목없음')}</div>
                        <div class="card-period">{ev.get('period', '기간 정보 확인 중')}</div>
                        <div class="card-footer">
                            <a href="{ev.get('lounge_link', '#')}" target="_blank" class="btn btn-lounge">공지 확인</a>
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
    <title>Game Event Schedule</title>
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
        exit(1)

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        
        # 모델 선택 로직 안정화
        model = None
        for m_name in ['gemini-2.0-flash', 'gemini-pro-latest', 'gemini-flash-latest']:
            try:
                temp_model = genai.GenerativeModel(m_name)
                temp_model.generate_content("test", generation_config={"max_output_tokens": 1})
                model = temp_model
                print(f"🤖 {m_name} 모델 연결 성공!")
                break
            except: continue

        if not model:
            print("❌ 어떠한 AI 모델도 활성화할 수 없습니다.")
            exit(1)

        final_all_events = []
        for lounge_id, info in LOUNGES.items():
            print(f"🚀 {info['name']} 정밀 데이터 수집 중...")
            raw_data = collect_game_data(lounge_id, info)
            
            if raw_data:
                game_events = analyze_game_events(info['name'], raw_data, model)
                if game_events:
                    final_all_events.extend(game_events)
            time.sleep(1)

        print(f"📦 총 {len(final_all_events)}개의 이벤트를 HTML로 구성 중입니다...")
        generate_html(final_all_events)
        print("✨ 모든 데이터 동기화 완료!")
        
    except Exception as e:
        print(f"‼️ 메인 루프 실행 중 치명적 오류: {e}")
        exit(1)
