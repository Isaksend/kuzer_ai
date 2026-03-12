import sys
import json
import csv
import cv2
import time
import asyncio
import threading
import numpy as np
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Добавляем корень проекта в path, чтобы импортировать config / logger / telegram
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import (
    VIDEO_SOURCE, ZONES_FILE, INCIDENTS_DIR, LOG_FILE,
    MODEL_PATH, CONFIDENCE_THRESHOLD, ZONE_COLORS,
    DELAY_SECONDS, DASHBOARD_HOST, DASHBOARD_PORT,
)

app = FastAPI(title="Zone Monitor Dashboard")

# ── Static files (для скриншотов инцидентов) ────────────────────
Path(INCIDENTS_DIR).mkdir(exist_ok=True)
app.mount("/incidents", StaticFiles(directory=INCIDENTS_DIR), name="incidents")

# ── Shared state ────────────────────────────────────────────────
latest_frame_bytes = None  # JPEG bytes текущего кадра
frame_lock = threading.Lock()


# ── Background video processing ────────────────────────────────
def video_worker():
    """Фоновый поток: YOLO + трекинг + отрисовка зон → encode в JPEG."""
    global latest_frame_bytes
    from ultralytics import YOLO
    from logger import IncidentLogger
    from telegram_notifier import TelegramNotifier

    model = YOLO(MODEL_PATH)
    logger_instance = IncidentLogger()
    telegram = TelegramNotifier()

    zones = _load_zones()
    alarm_timers = {}
    zone_durations = {}

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"[Dashboard] Cannot open video: {VIDEO_SOURCE}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    delay = 1.0 / fps

    print(f"[Dashboard] Video worker started. FPS={fps:.0f}, zones={len(zones)}")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        current_time = time.time()
        results = model.track(frame, persist=True, classes=[0], conf=CONFIDENCE_THRESHOLD, verbose=False)

        active_ids = set()

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            ids = results[0].boxes.id.cpu().numpy()

            for box, obj_id in zip(boxes, ids):
                x1, y1, x2, y2 = map(int, box)
                foot = ((x1 + x2) // 2, y2)
                active_ids.add(obj_id)

                triggered = [z for z in zones if cv2.pointPolygonTest(z["polygon"], foot, False) >= 0]

                if triggered:
                    alarm_timers[obj_id] = current_time

                    # Время в зоне
                    if obj_id not in zone_durations:
                        zone_durations[obj_id] = {"enter": current_time, "total": 0.0}
                    elif zone_durations[obj_id]["enter"] is None:
                        zone_durations[obj_id]["enter"] = current_time

                    dur = zone_durations[obj_id]["total"]
                    if zone_durations[obj_id]["enter"] is not None:
                        dur += current_time - zone_durations[obj_id]["enter"]

                    color = triggered[0]["color"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.circle(frame, foot, 5, color, -1)
                    cv2.putText(frame, f"ID:{int(obj_id)} | {dur:.0f}s", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                    for z in triggered:
                        logger_instance.log_incident(frame, obj_id, z["name"], current_time)
                        telegram.notify(frame, obj_id, z["name"], current_time)
                else:
                    if obj_id in zone_durations and zone_durations[obj_id]["enter"] is not None:
                        zone_durations[obj_id]["total"] += current_time - zone_durations[obj_id]["enter"]
                        zone_durations[obj_id]["enter"] = None

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    cv2.circle(frame, foot, 5, (255, 0, 0), -1)
                    cv2.putText(frame, f"ID:{int(obj_id)}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

        for oid in list(zone_durations):
            if oid not in active_ids and zone_durations[oid]["enter"] is not None:
                zone_durations[oid]["total"] += current_time - zone_durations[oid]["enter"]
                zone_durations[oid]["enter"] = None

        expired = [oid for oid, t in alarm_timers.items() if current_time - t > DELAY_SECONDS]
        for oid in expired:
            del alarm_timers[oid]

        # Рисуем зоны
        overlay = frame.copy()
        for zone in zones:
            pts = zone["polygon"].reshape((-1, 1, 2))
            color = zone["color"]
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
            cv2.fillPoly(overlay, [pts], color)
            cx = int(np.mean(zone["polygon"][:, 0]))
            cy = int(np.mean(zone["polygon"][:, 1]))
            cv2.putText(frame, zone["name"], (cx - 30, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

        # ALARM
        if alarm_timers:
            h, w = frame.shape[:2]
            txt = "ALARM!"
            sz = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 3, 5)[0]
            x, y = (w - sz[0]) // 2, (h + sz[1]) // 4
            cv2.rectangle(frame, (x - 10, y - sz[1] - 10), (x + sz[0] + 10, y + 10), (0, 0, 0), -1)
            cv2.putText(frame, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 5)

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        with frame_lock:
            latest_frame_bytes = buf.tobytes()

        time.sleep(delay)

    cap.release()


def _load_zones():
    try:
        with open(ZONES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return []

    if "zones" in data:
        return [
            {
                "name": z.get("name", f"Zone_{i+1}"),
                "polygon": np.array(z["points"], np.int32),
                "color": ZONE_COLORS[i % len(ZONE_COLORS)],
            }
            for i, z in enumerate(data["zones"])
        ]
    if "zone" in data:
        return [{"name": "Zone_1", "polygon": np.array(data["zone"], np.int32), "color": ZONE_COLORS[0]}]
    return []


# ── REST API ────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/api/incidents")
async def get_incidents():
    if not Path(LOG_FILE).exists():
        return JSONResponse([])
    rows = []
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return JSONResponse(rows[-50:][::-1])


@app.get("/api/zones")
async def get_zones():
    if not Path(ZONES_FILE).exists():
        return JSONResponse({"zones": []})
    with open(ZONES_FILE, 'r', encoding='utf-8') as f:
        return JSONResponse(json.load(f))


@app.post("/api/zones")
async def save_zones_api(request_body: dict):
    with open(ZONES_FILE, 'w', encoding='utf-8') as f:
        json.dump(request_body, f, indent=4, ensure_ascii=False)
    return JSONResponse({"status": "ok", "count": len(request_body.get("zones", []))})


# ── WebSocket Video Stream ──────────────────────────────────────
@app.websocket("/ws/video")
async def video_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            with frame_lock:
                data = latest_frame_bytes
            if data:
                await websocket.send_bytes(data)
            await asyncio.sleep(0.04)
    except WebSocketDisconnect:
        pass


# ── Startup ─────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    thread = threading.Thread(target=video_worker, daemon=True)
    thread.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=DASHBOARD_HOST, port=DASHBOARD_PORT, reload=False)
