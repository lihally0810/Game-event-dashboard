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

# 게임별 라운지 및 게시판 정보
LOUNGES = {
    "WutheringWaves": {"name": "명조: 워더링 웨이브", "boards": [1, 3]},
    "ZZZ": {"name": "젠레스 존 제로", "boards": [11, 13]},
    "Trickcal": {"name": "트릭컬: 리바이브", "boards": [3, 13]}
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
                    "content_preview": feed["feed"].get("contents", "")[:500]
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
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
너는 게임 데이터 분석가야. 아래 제공된 네이버 게임 라운지 데이터를 분석해서 한정 이벤트 정보를 JSON 배열로 반환해줘.

### 데이터:
{json.dumps(raw_data, ensure_ascii=False)}

### 🔍 추출 규칙:
1. **오늘 날짜**: {datetime.now().strftime('%Y-%m-%d')}
2. **포함**: 기간 한정 이벤트, 웹 이벤트, 콜라보레이션.
3. **제외**: 출석체크(로그인 보상), 상시/정규 이벤트, 업데이트 알림.
4. **상태**: 3일 이내 마감이면 `is_urgent: true`, 종료되었으면 `is_expired: true`.

### ✍️ 출력 형식 (유효한 JSON 배열만 출력):
[
  {{
    "game": "게임명",
    "title": "이벤트 명",
    "period": "시작일 ~ 종료일",
    "lounge_link": "원본 게시글 링크",
    "web_link": "이벤트 참여 링크(없으면 null)",
    "is_urgent": true/false,
    "is_expired": true/false
  }},
  ...
]
"""
    try:
        response = model.generate_content(prompt)
        res_text = response.text.strip()
        
        # JSON 문자열 추출 (마크다운 코드 블록 제거)
        if res_text.startswith("```"):
            res_text = res_text.split("```")[1]
            if res_text.startswith("json"):
                res_text = res_text[4:]
        
        events_list = json.loads(res_text.strip())
        print(f"🤖 AI가 이벤트를 {len(events_list)}개 추출했습니다.")
        return events_list
    except Exception as e:
        print(f"❌ LLM 처리 중 오류: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"🔍 AI 원본 응답 요약: {response.text[:100]}...")
        return []

def generate_html(events):
    # CSS 읽기
    css_content = ""
    try:
        with open("style.css", "r", encoding="utf-8") as f:
            css_content = f.read()
    except:
        print("⚠️ style.css를 찾을 수 없습니다.")

    # HTML 템플릿
    html_template = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Game Event Tracker</title>
    <style>{css_content}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>GAME EVENT TRACKER</h1>
            <div class="date-badge">Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        </header>

        <div id="dashboard">
            {{sections}}
        </div>
    </div>
</body>
</html>
"""
    
    # 게임별 섹션 생성
    sections = ""
    grouped_events = {}
    for ev in events:
        game_name = ev.get("game", "기타")
        if game_name not in grouped_events:
            grouped_events[game_name] = []
        grouped_events[game_name].append(ev)

    if not grouped_events:
        sections = """
        <div class="empty-state">
            <p>현재 표시할 이벤트가 없습니다.</p>
            <p><small>GitHub Secrets에 <b>GOOGLE_API_KEY</b>가 올바르게 등록되어 있는지 확인해 주세요.</small></p>
        </div>
        """
    else:
        for game, ev_list in grouped_events.items():
            cards = ""
            for ev in ev_list:
                urgent_tag = '<div class="urgent-tag">⚠️ 마감 임박</div>' if ev.get("is_urgent") else ""
                expired_cls = "expired" if ev.get("is_expired") else ""
                web_btn = f'<a href="{ev["web_link"]}" target="_blank" class="btn btn-web">참여하기</a>' if ev.get("web_link") else ""
                
                cards += f"""
                <div class="event-card {expired_cls}">
                    {urgent_tag}
                    <div class="event-title">{ev['title']}</div>
                    <div class="event-period">{ev['period']}</div>
                    <div class="event-actions">
                        <a href="{ev['lounge_link']}" target="_blank" class="btn btn-lounge">라운지</a>
                        {web_btn}
                    </div>
                </div>
                """
            
            sections += f"""
            <div class="game-section">
                <div class="game-title">{game}</div>
                <div class="event-grid">{cards}</div>
            </div>
            """

    final_html = html_template.replace("{sections}", sections)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    print("✨ index.html 생성 완료!")

if __name__ == "__main__":
    print("🚀 데이터 수집 시작...")
    raw_data = collect_all_data()
    
    print("🤖 AI 분석 중 (JSON 변환)...")
    events = get_events_json(raw_data)
    
    if not events:
        print("ℹ️ 새로운 이벤트가 없습니다. 빈 대시보드를 생성합니다.")
    
    print(f"📦 {len(events)}개의 이벤트를 처리 중입니다. HTML을 생성합니다...")
    generate_html(events)
