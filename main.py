import cv2
import json
import time
import numpy as np
from ultralytics import YOLO
from config import (
    VIDEO_SOURCE, ZONES_FILE, WINDOW_NAME,
    ALARM_TEXT, ALARM_COLOR, DELAY_SECONDS,
    MODEL_PATH, CONFIDENCE_THRESHOLD, ZONE_COLORS,
)
from logger import IncidentLogger


class ZoneMonitor:
    def __init__(self):
        self.model = YOLO(MODEL_PATH)
        self.zones = self._load_zones()
        self.alarm_timers = {}  # {obj_id: timestamp}
        self.logger = IncidentLogger()

    # ── Загрузка зон ────────────────────────────────────────────────
    def _load_zones(self):
        """Загружает зоны из JSON. Поддерживает и старый, и новый формат."""
        try:
            with open(ZONES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Zone file '{ZONES_FILE}' not found. Run zone_selector.py first.")
            return []

        # Новый формат: {"zones": [{...}, ...]}
        if "zones" in data:
            zones = []
            for i, z in enumerate(data["zones"]):
                zones.append({
                    "name": z.get("name", f"Zone_{i+1}"),
                    "polygon": np.array(z["points"], np.int32),
                    "color": ZONE_COLORS[i % len(ZONE_COLORS)],
                })
            return zones

        # Обратная совместимость: старый формат {"zone": [[x,y], ...]}
        if "zone" in data:
            return [{
                "name": "Zone_1",
                "polygon": np.array(data["zone"], np.int32),
                "color": ZONE_COLORS[0],
            }]

        print("Invalid zone file format.")
        return []

    # ── Геометрия ───────────────────────────────────────────────────
    @staticmethod
    def _point_in_polygon(polygon, point):
        return cv2.pointPolygonTest(polygon, point, False) >= 0

    def _check_zones(self, point):
        """Возвращает список зон, в которые попала точка."""
        triggered = []
        for zone in self.zones:
            if self._point_in_polygon(zone["polygon"], point):
                triggered.append(zone)
        return triggered

    # ── Отрисовка ───────────────────────────────────────────────────
    def _draw_zones(self, frame):
        overlay = frame.copy()
        for zone in self.zones:
            pts = zone["polygon"].reshape((-1, 1, 2))
            color = zone["color"]
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
            cv2.fillPoly(overlay, [pts], color)
            # Имя зоны в центре
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
        x = (w - sz[0]) // 2
        y = (h + sz[1]) // 4
        # Фон-подложка для читаемости
        cv2.rectangle(frame, (x - 10, y - sz[1] - 10), (x + sz[0] + 10, y + 10), (0, 0, 0), -1)
        cv2.putText(frame, ALARM_TEXT, (x, y), font, scale, ALARM_COLOR, thick)

    # ── Основной цикл ──────────────────────────────────────────────
    def run(self):
        if not self.zones:
            return

        cap = cv2.VideoCapture(VIDEO_SOURCE)
        if not cap.isOpened():
            print(f"Error opening video: {VIDEO_SOURCE}")
            return

        print(f"Running Tracker on {len(self.zones)} zone(s). Press 'q' to exit.")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            current_time = time.time()
            alarm_active = False

            # ── YOLO + трекинг ──────────────────────────────────────
            results = self.model.track(
                frame, persist=True, classes=[0],
                conf=CONFIDENCE_THRESHOLD, verbose=False,
            )

            if results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids = results[0].boxes.id.cpu().numpy()

                for box, obj_id in zip(boxes, ids):
                    x1, y1, x2, y2 = map(int, box)
                    foot_point = ((x1 + x2) // 2, y2)

                    triggered_zones = self._check_zones(foot_point)

                    if triggered_zones:
                        self.alarm_timers[obj_id] = current_time
                        color = triggered_zones[0]["color"]
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.circle(frame, foot_point, 5, color, -1)
                        cv2.putText(frame, f"ID:{int(obj_id)}", (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                        # Логируем инцидент (со скриншотом)
                        for z in triggered_zones:
                            self.logger.log_incident(frame, obj_id, z["name"], current_time)
                    else:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                        cv2.circle(frame, foot_point, 5, (255, 0, 0), -1)
                        cv2.putText(frame, f"ID:{int(obj_id)}", (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

            # ── Логика удержания тревоги 3 сек ──────────────────────
            expired = [oid for oid, t in self.alarm_timers.items()
                       if current_time - t > DELAY_SECONDS]
            for oid in expired:
                del self.alarm_timers[oid]

            if self.alarm_timers:
                alarm_active = True

            # ── Отрисовка ───────────────────────────────────────────
            self._draw_zones(frame)
            if alarm_active:
                self._draw_alarm(frame)

            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    monitor = ZoneMonitor()
    monitor.run()
