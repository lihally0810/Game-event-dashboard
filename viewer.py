import sys
import os
import pandas as pd
import json
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl
from datetime import datetime

class GameEventViewer(QMainWindow):
    def __init__(self, excel_path="game_events.xlsx"):
        super().__init__()
        self.setWindowTitle("Game Event Tracker")
        self.setGeometry(100, 100, 1280, 800)
        
        self.browser = QWebEngineView()
        self.setCentralWidget(self.browser)
        
        self.excel_path = excel_path
        self.load_data_and_render()

    def load_data_and_render(self):
        if not os.path.exists(self.excel_path):
            self.browser.setHtml("<h1>⚠️ 데이터를 찾을 수 없습니다.</h1><p>/update 명령어를 먼저 실행해주세요.</p>")
            return

        try:
            df = pd.read_excel(self.excel_path)
            events = df.to_dict('records')
            self.render_html(events)
        except Exception as e:
            self.browser.setHtml(f"<h1>❌ 데이터 로드 오류</h1><p>{str(e)}</p>")

    def render_html(self, events):
        # CSS 파일 읽기
        css_content = ""
        css_path = os.path.join(os.path.dirname(__file__), "style.css")
        if os.path.exists(css_path):
            with open(css_path, "r", encoding="utf-8") as f:
                css_content = f.read()

        # 데이터 그룹화
        grouped = {}
        for ev in events:
            g = ev.get("game", "기타")
            c = ev.get("category", "기타")
            if g not in grouped: grouped[g] = {}
            if c not in grouped[g]: grouped[g][c] = []
            grouped[g][c].append(ev)

        # 게임 목록 (사이드바용)
        games_list = list(grouped.keys())
        
        sidebar_items = ""
        main_contents = ""
        
        for i, game_name in enumerate(games_list):
            active_cls = "active" if i == 0 else ""
            lounge_key = f"game_{i}"
            sidebar_items += f'<button class="sidebar-item {active_cls}" onclick="switchGame(\'{lounge_key}\', this)">{game_name}</button>'
            
            game_events = grouped.get(game_name, {})
            section_content = f'<h2 class="section-game-title">{game_name}</h2>'
            
            kanban_grid = ""
            for category in ['인 게임', '커뮤니티', '오프라인']:
                ev_list = game_events.get(category, [])
                if not ev_list and category != '인 게임': continue
                
                cards = ""
                for ev in ev_list:
                    urgent_tag = '<span class="tag-urgent">마감 임박</span>' if str(ev.get("is_urgent")).lower() == 'true' else ""
                    web_btn = f'<a href="{ev.get("web_link")}" target="_blank" class="btn btn-web">참여 페이지</a>' if pd.notna(ev.get("web_link")) and ev.get("web_link") else ""
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
            main_contents += f'<div id="{lounge_key}" class="game-content" style="{display_style}">{section_content}</div>'

        html_template = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>Game Event Viewer</title>
    <style>{css_content}</style>
    <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body>
    <div class="app-layout">
        <aside class="sidebar">
            <div class="sidebar-header">EVENT TRACKER</div>
            <nav class="sidebar-nav">{sidebar_items}</nav>
            <div class="sidebar-footer">
                <div class="update-time">데이터 기반 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </aside>
        <main class="main-container">{main_contents}</main>
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
        self.browser.setHtml(html_template)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 인자로 엑셀 파일 경로를 받을 수 있게 함 (기본값 game_events.xlsx)
    path = sys.argv[1] if len(sys.argv) > 1 else "game_events.xlsx"
    viewer = GameEventViewer(path)
    viewer.show()
    sys.exit(app.exec_())
