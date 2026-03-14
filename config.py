import os
from pathlib import Path
from dotenv import load_dotenv

# Корень проекта — всегда папка, где лежит этот config.py
PROJECT_ROOT = Path(__file__).resolve().parent

# Загружаем .env из корня проекта (работает из любой CWD)
load_dotenv(PROJECT_ROOT / ".env")

# ── Источник видео ──────────────────────────────────────────────
# Можно указать путь к файлу, RTSP URL, или HTTP URL
# Примеры:
#   VIDEO_SOURCE = "test.mp4"
#   VIDEO_SOURCE = "rtsp://admin:pass@192.168.1.100:554/stream"
#   VIDEO_SOURCE = "http://192.168.1.100:8080/video"
VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", str(PROJECT_ROOT / "test.mp4"))

ZONES_FILE = str(PROJECT_ROOT / "restricted_zones.json")
INCIDENTS_DIR = str(PROJECT_ROOT / "incidents")
UPLOADS_DIR = str(PROJECT_ROOT / "uploads")

# Настройки камеры / окна
WINDOW_NAME = "Zone Monitor"
ALARM_TEXT = "ALARM!"
ALARM_COLOR = (0, 0, 255)  # BGR: Красный
DELAY_SECONDS = 3.0

# Настройки модели
MODEL_PATH = str(PROJECT_ROOT / "yolov8n.pt")
CONFIDENCE_THRESHOLD = 0.5

# Логирование
LOG_FILE = str(PROJECT_ROOT / "incidents" / "log.csv")
SCREENSHOT_COOLDOWN = 5.0

# Звук тревоги (Windows)
ALARM_SOUND_FREQ = 1500   # Гц
ALARM_SOUND_DURATION = 200  # мс

# Видеозапись инцидентов
RING_BUFFER_SECONDS = 10  # Секунд до инцидента
POST_RECORD_SECONDS = 10  # Секунд после инцидента

# Цвета зон (BGR)
ZONE_COLORS = [
    (0, 0, 255),    # Красный
    (0, 165, 255),  # Оранжевый
    (0, 255, 255),  # Жёлтый
    (255, 0, 255),  # Пурпурный
    (255, 0, 0),    # Синий
]

# Dashboard
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))


def source_key(source):
    """
    Возвращает ключ для привязки зон к источнику видео.
    Для файлов — имя файла (basename), для RTSP/HTTP — полный URL.
    """
    s = str(source)
    if s.startswith(("rtsp://", "http://", "https://")):
        return s
    return os.path.basename(s)

