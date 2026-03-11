import os

# Пути к файлам
VIDEO_SOURCE = "test.mp4"
ZONES_FILE = "restricted_zones.json"

# Настройки камеры / окна
WINDOW_NAME = "Zone Monitor"
ALARM_TEXT = "ALARM!"
ALARM_COLOR = (0, 0, 255) # BGR: Красный
DELAY_SECONDS = 3.0

# Настройки модели
MODEL_PATH = "yolov8n.pt" # Можно заменить на yolov11n.pt, если доступно
CONFIDENCE_THRESHOLD = 0.5
