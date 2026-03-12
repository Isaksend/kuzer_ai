import os
import cv2
import csv
from datetime import datetime
from config import INCIDENTS_DIR, LOG_FILE, SCREENSHOT_COOLDOWN


class IncidentLogger:
    """Логирует проникновения в запрещенные зоны: CSV-запись + скриншот кадра."""

    def __init__(self):
        os.makedirs(INCIDENTS_DIR, exist_ok=True)
        self._init_csv()
        # {obj_id: last_screenshot_time} — чтобы не спамить скриншотами
        self.screenshot_timers = {}

    def _init_csv(self):
        """Создаёт CSV-файл с заголовками, если его ещё нет."""
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "object_id", "zone_name", "screenshot"])

    def log_incident(self, frame, obj_id, zone_name, current_time):
        """
        Записывает инцидент в CSV и сохраняет скриншот.
        Скриншот сохраняется не чаще чем раз в SCREENSHOT_COOLDOWN секунд
        для одного и того же obj_id, чтобы не засорять диск.
        """
        last_time = self.screenshot_timers.get(obj_id, 0)
        if current_time - last_time < SCREENSHOT_COOLDOWN:
            return  # Слишком рано для повторного скриншота этого ID

        self.screenshot_timers[obj_id] = current_time

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_id{int(obj_id)}_{zone_name}.jpg"
        filepath = os.path.join(INCIDENTS_DIR, filename)

        cv2.imwrite(filepath, frame)

        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, int(obj_id), zone_name, filename])

        print(f"[INCIDENT] {timestamp} | ID: {int(obj_id)} | Zone: {zone_name} | Screenshot: {filename}")
