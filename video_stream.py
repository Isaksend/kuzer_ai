import cv2
import threading
import time
from collections import deque


class VideoStream:
    """
    Потокобезопасное чтение кадров из видео / RTSP / IP-камеры.
    Отделяет I/O от инференса, чтобы не терять FPS.
    Хранит кольцевой буфер последних N секунд для видеозаписи инцидентов.
    """

    def __init__(self, source, buffer_seconds=10):
        self.source = source
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {source}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._frame = None
        self._lock = threading.Lock()
        self._stopped = False
        self.is_done = False

        # Кольцевой буфер для записи «чёрного ящика»
        buf_size = int(self.fps * buffer_seconds)
        self._ring_buffer = deque(maxlen=buf_size)
        self._ring_lock = threading.Lock()

        # FPS measurement
        self._frame_count = 0
        self._fps_start = time.time()
        self.measured_fps = 0.0

        # Запуск потока чтения
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        target_frame_time = 1.0 / self.fps if self.fps > 0 else 0.04
        while not self._stopped:
            loop_start = time.time()
            ret, frame = self.cap.read()
            if not ret:
                # Для файлов — конец файла, больше не читаем
                if self._is_file():
                    self.is_done = True
                    break
                else:
                    # Для RTSP — попытаться переподключиться
                    time.sleep(1.0)
                    self.cap.release()
                    self.cap = cv2.VideoCapture(self.source)
                    continue

            with self._lock:
                self._frame = frame

            with self._ring_lock:
                self._ring_buffer.append(frame.copy())

            self._frame_count += 1
            elapsed = time.time() - self._fps_start
            if elapsed >= 1.0:
                self.measured_fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_start = time.time()
                
            # Искусственная задержка для видеофайлов, чтобы они проигрывались 1x Real-time
            if self._is_file():
                processing_time = time.time() - loop_start
                sleep_time = target_frame_time - processing_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def read(self):
        """Возвращает последний прочитанный кадр (без блокировки I/O)."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def get_ring_buffer(self):
        """Возвращает копию кольцевого буфера (для записи инцидентов)."""
        with self._ring_lock:
            return list(self._ring_buffer)

    def _is_file(self):
        return not str(self.source).startswith(("rtsp://", "http://", "https://"))

    def stop(self):
        self._stopped = True
        self._thread.join(timeout=3)
        self.cap.release()
