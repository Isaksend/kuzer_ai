import os
import io
import cv2
import threading
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Загружаем .env из корня проекта (рядом с config.py)
load_dotenv(Path(__file__).resolve().parent / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_COOLDOWN = 10.0  # Секунд между сообщениями для одного ID


class TelegramNotifier:
    """Отправляет уведомления в Telegram с фото и описанием инцидента."""

    def __init__(self):
        self.enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        self._cooldowns = {}  # {obj_id: last_send_time}

        if not self.enabled:
            print("[Telegram] Bot token or chat ID not set in .env — notifications disabled.")

    def notify(self, frame, obj_id, zone_name, current_time):
        """Отправляет уведомление, если прошёл cooldown для данного ID."""
        if not self.enabled:
            return

        last = self._cooldowns.get(obj_id, 0)
        if current_time - last < TELEGRAM_COOLDOWN:
            return

        self._cooldowns[obj_id] = current_time

        # Отправляем в отдельном потоке, чтобы не блокировать видеопоток
        thread = threading.Thread(
            target=self._send, args=(frame.copy(), obj_id, zone_name), daemon=True
        )
        thread.start()

    def _send(self, frame, obj_id, zone_name):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        caption = (
            f"🚨 <b>INTRUSION DETECTED</b>\n"
            f"📅 {timestamp}\n"
            f"👤 Object ID: {int(obj_id)}\n"
            f"📍 Zone: {zone_name}"
        )

        # Кодируем кадр в JPEG в памяти
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        photo = io.BytesIO(buf.tobytes())
        photo.name = "incident.jpg"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        try:
            resp = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"photo": photo},
                timeout=10,
            )
            if resp.ok:
                print(f"[Telegram] Notification sent for ID:{int(obj_id)} in {zone_name}")
            else:
                print(f"[Telegram] Error: {resp.status_code} — {resp.text[:120]}")
        except Exception as e:
            print(f"[Telegram] Send failed: {e}")
