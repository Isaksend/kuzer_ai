# Zone Monitor (YOLOv8 + OpenCV + FastAPI)

A restricted zone monitoring system for video streams with RTSP support. Uses YOLOv8 for detection and tracking, OpenCV for visualization, and FastAPI for a web-based real-time dashboard.

## Features

| #  | Feature | Status |
|----|---------|--------|
| 1  | Zone Selection (OpenCV GUI + Web Editor) | ✅ |
| 2  | YOLO Detection + BoT-SORT Tracking | ✅ |
| 3  | ALARM! with a 3-second delay | ✅ |
| 4  | Sound Notification (Windows) | ✅ |
| 5  | Incident Logging (CSV + screenshots) | ✅ |
| 6  | Telegram Bot Alerts (photo + description) | ✅ |
| 7  | Per-Zone Time Tracking (Zone Duration) | ✅ |
| 8  | RTSP / IP-Camera Support | ✅ |
| 9  | Video Upload to Service | ✅ |
| 10 | FPS Optimization (Multithreading) | ✅ |
| 11 | Incident Video Recording (Blackbox 10s pre/post) | ✅ |
| 12 | Analytics Dashboard (Charts & Top Offenders) | ✅ |
| 13 | Live Web Dashboard (Video Stream + Control) | ✅ |

## Project Structure
```
zone_monitor/
├── .env                    # Telegram tokens, RTSP URL, Port
├── .gitignore
├── config.py               # Global configuration (absolute paths)
├── zone_selector.py        # Zone selection (OpenCV GUI)
├── main.py                 # Main tracking script (OpenCV Window)
├── logger.py               # CSV logging + Screenshots
├── telegram_notifier.py    # Telegram alerts (Threaded)
├── video_stream.py         # Threaded frame capture (Ring buffer)
├── video_recorder.py       # Blackbox incident recording
├── analytics.py            # Generates logic for Analytics reports
├── requirements.txt
├── dashboard/
│   ├── app.py              # FastAPI + WebSockets + REST API
│   └── index.html          # Web interface (4 tabs)
├── incidents/
│   ├── log.csv             # Incidents log
│   ├── *.jpg               # Incident screenshots
│   └── recordings/         # Recorded incident videos
├── uploads/                # Uploaded video files
└── restricted_zones.json   # Saved zone coordinates (Per-video)
```

## Installation

```bash
python -m venv venv
venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

## .env Configuration

```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8000
# VIDEO_SOURCE=rtsp://admin:pass@192.168.1.100:554/stream
```

## Usage

### 1. Zone Selection (OpenCV)
```bash
python zone_selector.py
```

### 2. Monitoring (Local OpenCV Window)
```bash
# Default file (test.mp4)
python main.py

# Live from RTSP Stream
python main.py rtsp://admin:pass@192.168.1.100:554/stream
```

### 3. Web Dashboard
```bash
cd dashboard
python app.py
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

#### Dashboard Tabs:
- **📹 Monitor** — Live video stream + incidents feed + active zones count.
- **📊 Analytics** — Hourly charts, incidents per zone, top offenders list.
- **🎬 Recordings** — Playback recorded incident videos (10s before + 10s after).
- **⚙️ Settings** — Connect to RTSP, Upload new video files, Reset to default source.

## Architecture Pipeline

```text
┌──────────────┐     ┌─────────────┐     ┌───────────┐
│ VideoStream  │────>│  YOLO + Track│────>│ Overlay   │
│ (I/O thread) │     │  (main/worker)│     │ + Encode  │
│  ring buffer │     └──────┬───────┘     └─────┬─────┘
└──────────────┘            │                    │
                   ┌────────▼────────┐   ┌──────▼──────┐
                   │ Logger / Telegram│   │  WebSocket  │
                   │ VideoRecorder    │   │  → Browser  │
                   └─────────────────┘   └─────────────┘
```
