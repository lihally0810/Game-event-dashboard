import sys
import traceback

# 초기 에러 트래픽 캡처
print("🚀 [DEBUG] 시스템 시작 중...")

try:
    import requests
    from bs4 import BeautifulSoup
    import json
    import os
    import time
    from datetime import datetime
    import google.generativeai as genai
    from dotenv import load_dotenv

    load_dotenv()
    print("✅ [DEBUG] 필수 라이브러리 로드 완료")

except ImportError as e:
    print(f"❌ [DEBUG] 라이브러리 로드 실패: {e}")
    sys.exit(1)

# 환경 변수 및 설정
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("❌ [DEBUG] 구글 API 키(GOOGLE_API_KEY)가 환경 변수에서 발견되지 않았습니다.")
else:
    print(f"✅ [DEBUG] 구글 API 키 확인됨 (길이: {len(GOOGLE_API_KEY)})")

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
    """게시글 상세 페이지 방문하여 본문 전체 텍스트 수집 (정밀 스캔)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code != 200:
            print(f"⚠️ [DEBUG] {url} 접속 실패 (HTTP {res.status_code})")
            return ""
        soup = BeautifulSoup(res.text, 'html.parser')
        content_area = soup.select_one(".se-viewer") or soup.select_one("div[class^='detail_contents']")
        if content_area:
            return content_area.get_text("\n", strip=True)
        return ""
    except Exception:
        print(f"⚠️ [DEBUG] {url} 본문 수집 중 예외 발생")
        traceback.print_exc()
        return ""

def collect_game_data(lounge_id, info):
    """각 게임별로 최신 5개 게시글에 대해 딥 스크래핑합니다 (디버깅 위해 수집량 일시 축소)"""
    all_game_feeds = []
    for board in info["boards"]:
        board_id = board["id"]
        url = f"https://game-api.naver.com/game/v1/lounge/{lounge_id}/feed?boardId={board_id}&page=1&pageSize=5"
        try:
            print(f"📡 [DEBUG] {info['name']} (Board {board_id}) API 요청 시도...")
            res = requests.get(url, timeout=15)
            if res.status_code != 200:
                print(f"⚠️ [DEBUG] API 응답 실패 (HTTP {res.status_code})")
                continue
            data = res.json()
            feeds = data.get("contents", {}).get("feeds", [])
            print(f"✅ [DEBUG] {len(feeds)}개의 피드를 찾았습니다.")
            
            for f in feeds:
                f_id = f.get('feed', {}).get('feedId')
                if not f_id: continue
                
                link = f"https://game.naver.com/lounge/{lounge_id}/board/detail/{f_id}"
                print(f"🔎 [DEBUG] {info['name']} 정밀 본문 스캔: {f['feed'].get('title', '...')[:15]}...")
                full_text = get_full_text(link)
                
                all_game_feeds.append({
                    "game": info["name"],
                    "title": f['feed'].get('title', '제목없음'),
                    "link": link,
                    "full_text": full_text
                })
                time.sleep(1.0) # 디버깅 시에는 더 넉넉한 대기 시간
        except Exception:
            print(f"❌ [DEBUG] {info['name']} 수집 중 치명적 오류")
            traceback.print_exc()
    return all_game_feeds

def analyze_game_events(game_name, raw_data, ai_model):
    """게임별 분할 AI 분석"""
    if not ai_model or not raw_data:
        print(f"⚠️ [DEBUG] {game_name}: 분석할 데이터가 없거나 모델이 없습니다.")
        return []

    prompt = f"""
너는 게임 데이터 분석 전문가야. 제공된 '{game_name}'의 전체 본문 데이터를 기반으로 현재 진행 중인 한정 이벤트 정보를 JSON 배열로 반환해.

### 데이터:
{json.dumps(raw_data, ensure_ascii=False)}

### 🔍 추출 규칙:
1. 오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}
2. 인게임/커뮤니티/오프라인 분류. (뽑기/미니게임은 무조건 '인 게임')
3. 날짜 필수: 'X월 X일 00:00' 형식 (진행 중 사용 금지)

### ✍️ 출력 형식 (반드시 유효한 JSON 배열만 출력):
[
  {{
    "game": "{game_name}",
    "category": "...",
    "title": "...",
    "period": "X월 X일 00:00 ~ X월 X일 00:00",
    "lounge_link": "...",
    "web_link": "...",
    "is_urgent": true/false
  }}
]
"""
    try:
        print(f"🤖 [DEBUG] {game_name} AI 분석 요청 중...")
        response = ai_model.generate_content(prompt)
        res_text = response.text.strip()
        
        if "```" in res_text:
            res_text = res_text.split("```")[1]
            if res_text.lower().startswith("json"):
                res_text = res_text[4:]
        
        res_text = res_text.strip()
        try:
            return json.loads(res_text)
        except json.JSONDecodeError:
            print(f"❌ [DEBUG] AI 응답 JSON 파싱 실패. 원문: \n{res_text}")
            return []
            
    except Exception:
        print(f"❌ [DEBUG] {game_name} AI 분석 중 에러 발생")
        traceback.print_exc()
        return []

def generate_html(events):
    print("🎨 [DEBUG] HTML 생성 중...")
    try:
        css_content = ""
        if os.path.exists("style.css"):
            with open("style.css", "r", encoding="utf-8") as f:
                css_content = f.read()
        
        # HTML 템플릿 로직 (압축)
        with open("index.html", "w", encoding="utf-8") as f:
            f.write("<html><body><h1>Debug Mode</h1><pre>" + json.dumps(events, indent=2, ensure_ascii=False) + "</pre></body></html>")
        print("✅ [DEBUG] index.html 저장 완료")
    except Exception:
        print("❌ [DEBUG] HTML 생성 실패")
        traceback.print_exc()

if __name__ == "__main__":
    try:
        # 모델 초기화 정밀 디버깅
        model = None
        for m_name in ['gemini-2.0-flash', 'gemini-pro-latest', 'gemini-flash-latest']:
            try:
                print(f"🤖 [DEBUG] {m_name} 모델 연결 시도...")
                temp_model = genai.GenerativeModel(m_name)
                temp_model.generate_content("test", generation_config={"max_output_tokens": 1})
                model = temp_model
                print(f"✅ [DEBUG] {m_name} 채택됨")
                break
            except Exception as e:
                print(f"⚠️ [DEBUG] {m_name} 실패 원인: {e}")

        if not model:
            print("❌ [DEBUG] 어떠한 AI 모델도 사용할 수 없습니다. API 키나 할당량을 확인하세요.")
            sys.exit(1)

        total_parsed_events = []
        for lounge_id, info in LOUNGES.items():
            print(f"\n--- {info['name']} 작업 시작 ---")
            raw = collect_game_data(lounge_id, info)
            if raw:
                evs = analyze_game_events(info['name'], raw, model)
                total_parsed_events.extend(evs)
        
        generate_html(total_parsed_events)
        print("\n✨ [DEBUG] 모든 디버깅 작업 완료!")

    except Exception:
        print("‼️ [DEBUG] 최상위 루프에서 예외 발생")
        traceback.print_exc()
        sys.exit(1)
