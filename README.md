# CareWave 대시보드 공유용 파일

이 브랜치는 `CareWave_sensor`의 대시보드 화면 구현 파일만 분리한 공유 패키지입니다. 운영용 `main` 브랜치에는 영향을 주지 않습니다.

## 포함된 파일
- `visualization/index.html` — 대시보드 화면 구조
- `visualization/dashboard.css` — 레이아웃과 스타일
- `visualization/dashboard.js` — 센서 상태 조회, 제어 버튼, 실시간 데이터 수신
- `visualization/dashboard3d.js` — Three.js 기반 3D 레이더 화면

## 실행 환경
이 파일들은 단독 HTML 파일로 더블클릭하여 완전히 동작하는 형태가 아니라, 기존 FastAPI 서버에 연결되는 **프런트엔드 구성 요소**입니다.

원본 서버는 `/dashboard`에 `index.html`을 제공하고 `/dashboard-static/`에 정적 파일을 연결합니다.
대시보드는 `/api/sensor/{sensor_id}/status`, `/api/sensor/{sensor_id}/command`, `/ws/sensor/{sensor_id}` 엔드포인트를 사용합니다.
3D 시각화는 Three.js 외부 모듈(CDN)을 로드합니다.

실제 화면을 사용하려면 원본 CareWave_sensor 서버의 `visualization` 폴더에 동일한 구조로 넣고, 기존 FastAPI 서버를 실행한 후 `/dashboard` 주소로 접속해야 합니다. 백엔드 API와 WebSocket을 다른 서버에서 제공한다면 별도의 연결 설정 또는 프록시가 필요합니다.

원본 저장소: https://github.com/wldnjs1126/CareWave_sensor
