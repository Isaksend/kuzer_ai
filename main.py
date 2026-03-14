import cv2
import json
import time
import threading
import numpy as np
from ultralytics import YOLO
from config import (
    VIDEO_SOURCE, ZONES_FILE, WINDOW_NAME,
    ALARM_TEXT, ALARM_COLOR, DELAY_SECONDS,
    MODEL_PATH, CONFIDENCE_THRESHOLD, ZONE_COLORS,
    ALARM_SOUND_FREQ, ALARM_SOUND_DURATION,
    RING_BUFFER_SECONDS, POST_RECORD_SECONDS,
    source_key,
)
from logger import IncidentLogger
from telegram_notifier import TelegramNotifier
from video_stream import VideoStream
from video_recorder import VideoRecorder

# Звук только на Windows
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class ZoneMonitor:
    def __init__(self, source=None):
        self.source = source or VIDEO_SOURCE
        self.model = YOLO(MODEL_PATH)
        self.zones = self._load_zones()
        self.alarm_timers = {}
        self.zone_durations = {}
        self.logger = IncidentLogger()
        self.telegram = TelegramNotifier()
        self._sound_playing = False

        # Threaded video stream
        self.stream = None
        self.recorder = None

    # ── Загрузка зон (per-video) ────────────────────────────────────
    def _load_zones(self):
        try:
            with open(ZONES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Zone file '{ZONES_FILE}' not found. Run zone_selector.py first.")
            return []

        key = source_key(self.source)

        # Новый формат: {source_key: {"zones": [...]}, ...}
        if key in data:
            zone_list = data[key].get("zones", [])
        elif "zones" in data and isinstance(data["zones"], list):
            # Старый формат: {"zones": [...]}
            zone_list = data["zones"]
        elif "zone" in data:
            # Совсем старый формат: {"zone": [...]}
            return [{
                "name": "Zone_1",
                "polygon": np.array(data["zone"], np.int32),
                "color": ZONE_COLORS[0],
            }]
        else:
            print(f"No zones found for source '{key}'.")
            return []

        return [
            {
                "name": z.get("name", f"Zone_{i+1}"),
                "polygon": np.array(z["points"], np.int32),
                "color": ZONE_COLORS[i % len(ZONE_COLORS)],
            }
            for i, z in enumerate(zone_list)
        ]

    # ── Геометрия ───────────────────────────────────────────────────
    @staticmethod
    def _point_in_polygon(polygon, point):
        return cv2.pointPolygonTest(polygon, point, False) >= 0

    def _check_zones(self, point):
        return [z for z in self.zones if self._point_in_polygon(z["polygon"], point)]

    # ── Звук (неблокирующий) ────────────────────────────────────────
    def _play_alarm_sound(self):
        if not HAS_WINSOUND or self._sound_playing:
            return
        self._sound_playing = True

        def _beep():
            try:
                winsound.Beep(ALARM_SOUND_FREQ, ALARM_SOUND_DURATION)
            finally:
                self._sound_playing = False

        threading.Thread(target=_beep, daemon=True).start()

    # ── Время в зоне ────────────────────────────────────────────────
    def _update_duration(self, obj_id, in_zone, current_time):
        if in_zone:
            if obj_id not in self.zone_durations:
                self.zone_durations[obj_id] = {"enter": current_time, "total": 0.0}
            elif self.zone_durations[obj_id]["enter"] is None:
                self.zone_durations[obj_id]["enter"] = current_time
        else:
            if obj_id in self.zone_durations and self.zone_durations[obj_id]["enter"] is not None:
                self.zone_durations[obj_id]["total"] += current_time - self.zone_durations[obj_id]["enter"]
                self.zone_durations[obj_id]["enter"] = None

    def _get_duration(self, obj_id, current_time):
        if obj_id not in self.zone_durations:
            return 0.0
        d = self.zone_durations[obj_id]
        total = d["total"]
        if d["enter"] is not None:
            total += current_time - d["enter"]
        return total

    # ── Отрисовка ───────────────────────────────────────────────────
    def _draw_zones(self, frame):
        overlay = frame.copy()
        for zone in self.zones:
            pts = zone["polygon"].reshape((-1, 1, 2))
            color = zone["color"]
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
            cv2.fillPoly(overlay, [pts], color)
            cx = int(np.mean(zone["polygon"][:, 0]))
            cy = int(np.mean(zone["polygon"][:, 1]))
            cv2.putText(frame, zone["name"], (cx - 30, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

    def _draw_alarm(self, frame):
        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale, thick = 3, 5
        sz = cv2.getTextSize(ALARM_TEXT, font, scale, thick)[0]
        x, y = (w - sz[0]) // 2, (h + sz[1]) // 4
        cv2.rectangle(frame, (x - 10, y - sz[1] - 10), (x + sz[0] + 10, y + 10), (0, 0, 0), -1)
        cv2.putText(frame, ALARM_TEXT, (x, y), font, scale, ALARM_COLOR, thick)

    def _draw_fps(self, frame):
        fps_text = f"FPS: {self.stream.measured_fps:.0f}"
        cv2.putText(frame, fps_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # ── Основной цикл ──────────────────────────────────────────────
    def run(self):
        if not self.zones:
            return

        try:
            self.stream = VideoStream(self.source, buffer_seconds=RING_BUFFER_SECONDS)
        except RuntimeError as e:
            print(e)
            return

        self.recorder = VideoRecorder(fps=self.stream.fps, post_seconds=POST_RECORD_SECONDS)

        print(f"Running Tracker on {len(self.zones)} zone(s). Source: {self.source}")
        print("Press 'q' to exit.")

        while True:
            if self.stream.is_done:
                print("Video stream reached end of file.")
                break

            frame = self.stream.read()
            if frame is None:
                time.sleep(0.01)
                continue

            current_time = time.time()

            # ── YOLO + трекинг (в основном потоке, чтение уже отделено) ──
            results = self.model.track(
                frame, persist=True, classes=[0],
                conf=CONFIDENCE_THRESHOLD, verbose=False,
            )

            active_ids = set()
            alarm_triggered_this_frame = False

            if results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids = results[0].boxes.id.cpu().numpy()

                for box, obj_id in zip(boxes, ids):
                    x1, y1, x2, y2 = map(int, box)
                    foot = ((x1 + x2) // 2, y2)
                    active_ids.add(obj_id)

                    triggered = self._check_zones(foot)

                    if triggered:
                        was_new = obj_id not in self.alarm_timers
                        self.alarm_timers[obj_id] = current_time
                        self._update_duration(obj_id, True, current_time)
                        alarm_triggered_this_frame = True
                        color = triggered[0]["color"]
                        dur = self._get_duration(obj_id, current_time)
                        label = f"ID:{int(obj_id)} | {dur:.0f}s"

                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.circle(frame, foot, 5, color, -1)
                        cv2.putText(frame, label, (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                        for z in triggered:
                            self.logger.log_incident(frame, obj_id, z["name"], current_time)
                            self.telegram.notify(frame, obj_id, z["name"], current_time)

                        # Запись видео при первом входе
                        if was_new:
                            ring = self.stream.get_ring_buffer()
                            self.recorder.record(ring, self.stream, key=f"{int(obj_id)}")
                    else:
                        self._update_duration(obj_id, False, current_time)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                        cv2.circle(frame, foot, 5, (255, 0, 0), -1)
                        cv2.putText(frame, f"ID:{int(obj_id)}", (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

            for oid in list(self.zone_durations):
                if oid not in active_ids:
                    self._update_duration(oid, False, current_time)

            # ── Логика удержания тревоги 3 сек ──────────────────────
            expired = [oid for oid, t in self.alarm_timers.items()
                       if current_time - t > DELAY_SECONDS]
            for oid in expired:
                del self.alarm_timers[oid]

            alarm_active = bool(self.alarm_timers)

            # ── Отрисовка ───────────────────────────────────────────
            self._draw_zones(frame)
            self._draw_fps(frame)
            if alarm_active:
                self._draw_alarm(frame)
                self._play_alarm_sound()

            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.stream.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else None
    monitor = ZoneMonitor(source=source)
    monitor.run()
