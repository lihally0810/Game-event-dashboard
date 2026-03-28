# 🎮 Game Event Dashboard Automation

네이버 게임 라운지(명조, ZZZ, 트릭컬)의 한정 이벤트를 자동으로 수집하여 보여주는 대시보드입니다. 
GitHub Actions를 통해 매일 아침 9시(KST)에 자동으로 가동됩니다.

## 🚀 시작하기 (배포 방법)

전체 자동화를 위해 아래 단계에 따라 설정을 완료해 주세요.

### 1단계: GitHub 저장소 만들기
1. [GitHub](https://github.com/)에 접속하여 새로운 저장소(New Repository)를 만듭니다.
2. 로컬 터미널에서 아래 명령어를 순서대로 입력하여 코드를 올립니다:
   ```bash
   git add .
   git commit -m "Initialize project"
   git branch -M main
   git remote add origin https://github.com/[사용자이름]/[저장소이름].git
   git push -u origin main
   ```

### 2단계: API 키 등록 (가장 중요!)
GitHub Actions가 작동하려면 Gemini API 키가 필요합니다.
1. GitHub 저장소의 **Settings** 탭으로 들어갑니다.
2. 왼쪽 메뉴에서 **Secrets and variables** -> **Actions**를 클릭합니다.
3. **New repository secret** 버튼을 누릅니다.
4. Name에 `GOOGLE_API_KEY`를 입력하고, Value에 사용자님의 API 키를 붙여넣은 뒤 **Add secret**을 누릅니다.

### 3단계: 웹사이트 활성화 (GitHub Pages)
1. 저장소의 **Settings** -> **Pages** 탭으로 이동합니다.
2. **Build and deployment** 섹션의 Branch가 `main`으로 설정되어 있는지 확인하고 **Save**를 누릅니다.
3. 약 2~3분 뒤 상단에 생성되는 `https://[username].github.io/[repo-name]/` 링크가 사용자님의 실시간 대시보드 주소입니다.

## ⏰ 자동화 일정
- **매일 오전 09:00 (KST)**: 새로운 이벤트 데이터를 수집하고 웹사이트를 자동 갱신합니다.
- **수동 실행**: GitHub 저장소의 **Actions** 탭에서 `Daily Game Event Update` 워크플로우를 선택한 뒤 `Run workflow`를 눌러 즉시 업데이트할 수 있습니다.

---
*본 프로젝트는 AI를 활용하여 제작되었으며, 네이버 게임 라운지 데이터를 기반으로 합니다.*
