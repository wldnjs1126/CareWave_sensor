# CareWave Sensor Ingest

IWR6843AOPEVM + XIAO ESP32-C6에서 전송한 레이더 프레임을 FastAPI가 수신하고, 프레임 원본은 DB에 저장하지 않은 채 1초 단위로 메모리에서 집계하여 Naver Cloud Platform MySQL의 `sensor_raw` 테이블에 저장하는 프로젝트입니다.

## 데이터 흐름

```text
IWR6843AOPEVM
  -> XIAO ESP32-C6 (UART/TLV parsing)
  -> Wi-Fi HTTP POST /api/sensor/frame
  -> FastAPI memory buffer (1 second)
  -> sensor_raw aggregation
  -> NCP MySQL
```

`radar_frame` 테이블은 사용하지 않습니다.

## sensor_raw 기준

현재 서버는 아래 집계값을 저장합니다.

- `sample_count`
- `presence`
- `avg_x`, `avg_y`, `avg_z`, `min_z`
- `avg_velocity_x`, `avg_velocity_y`, `avg_velocity_z`, `min_velocity_z`
- `avg_speed`, `max_speed`
- `avg_acceleration_z`, `min_acceleration_z`
- `avg_height`, `min_height`
- `avg_movement_level`
- `zone`
- `window_start`, `window_end`, `created_at`

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`.env.example`을 복사해 `.env`를 만들고 실제 NCP MySQL 접속 정보를 입력합니다.

```bash
copy .env.example .env
```

서버 실행:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

상태 확인:

```text
GET /health
```

프레임 수신:

```text
POST /api/sensor/frame
```

예시 요청:

```json
{
  "sensor_id": 1,
  "subject_id": 1,
  "frame_id": 353,
  "target_id": 1,
  "x": -0.105,
  "y": 3.280,
  "z": 0.075,
  "velocity_x": 0.034,
  "velocity_y": -0.069,
  "velocity_z": -0.008,
  "acceleration_z": 0.004,
  "speed": 0.078,
  "height": 0.138,
  "presence": true,
  "zone": "ROOM"
}
```

`speed`가 없으면 서버가 `velocity_x/y/z`로 계산합니다. `movement_level`이 없으면 `speed`를 사용합니다. `zone`이 없으면 DB에 `NULL`로 저장합니다.

## 주의

- `.env`는 GitHub에 올리지 않습니다.
- ESP32에는 DB 계정/비밀번호를 넣지 않습니다.
- ESP32는 FastAPI 주소만 알고 있으면 됩니다.
- 프레임 원본은 메모리에서 1초간만 보관되며, 집계 후 제거됩니다.
