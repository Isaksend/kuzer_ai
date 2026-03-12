import os

# Пути к файлам
VIDEO_SOURCE = "test.mp4"
ZONES_FILE = "restricted_zones.json"
INCIDENTS_DIR = "incidents"

# Настройки камеры / окна
WINDOW_NAME = "Zone Monitor"
ALARM_TEXT = "ALARM!"
ALARM_COLOR = (0, 0, 255) # BGR: Красный
DELAY_SECONDS = 3.0

# Настройки модели
MODEL_PATH = "yolov8n.pt"
CONFIDENCE_THRESHOLD = 0.5

# Настройки логирования
LOG_FILE = os.path.join(INCIDENTS_DIR, "incidents.csv")
SCREENSHOT_COOLDOWN = 5.0  # Минимум секунд между скриншотами одного и того же ID

# Цвета зон (BGR) — циклически используются при создании нескольких зон
ZONE_COLORS = [
    (0, 0, 255),    # Красный
    (0, 165, 255),  # Оранжевый
    (0, 255, 255),  # Жёлтый
    (255, 0, 255),  # Пурпурный
    (255, 0, 0),    # Синий
]
