import cv2
import os
import time
import threading
from datetime import datetime
from config import INCIDENTS_DIR


class VideoRecorder:
    """
    «Чёрный ящик»: при вызове record() сохраняет видеофрагмент
    из кольцевого буфера (до инцидента) + дозаписывает N секунд после.
    """

    def __init__(self, fps=25, post_seconds=10):
        self.fps = fps
        self.post_seconds = post_seconds
        self._recordings_dir = os.path.join(INCIDENTS_DIR, "recordings")
        os.makedirs(self._recordings_dir, exist_ok=True)
        self._cooldown = {}       # {key: last_record_time}
        self._cooldown_sec = 30   # Мин. интервал между записями

    def record(self, ring_buffer, stream, key="default"):
        """
        Запускает запись в фоновом потоке:
          1. ring_buffer — кадры ДО инцидента (из VideoStream)
          2. stream — VideoStream, из которого дочитываем кадры ПОСЛЕ
        """
        now = time.time()
        if now - self._cooldown.get(key, 0) < self._cooldown_sec:
            print(f"[Recorder] Cooldown active for key={key}, skipping.")
            return
        self._cooldown[key] = now

        # Копируем буфер сразу (он может измениться пока поток работает)
        pre_frames = list(ring_buffer) if ring_buffer else []
        print(f"[Recorder] Starting recording for key={key}, pre_frames={len(pre_frames)}")

        thread = threading.Thread(
            target=self._write, args=(pre_frames, stream), daemon=True
        )
        thread.start()

    def _write(self, pre_frames, stream):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        if not pre_frames:
            print("[Recorder] No pre-frames, nothing to record.")
            return

        h, w = pre_frames[0].shape[:2]

        # Пробуем несколько кодеков (mp4v может не работать на Windows)
        codecs = [
            ("mp4v", ".mp4"),
            ("XVID", ".avi"),
            ("MJPG", ".avi"),
        ]

        writer = None
        filepath = None

        for codec_name, ext in codecs:
            filename = f"incident_{timestamp}{ext}"
            filepath = os.path.join(self._recordings_dir, filename)
            fourcc = cv2.VideoWriter_fourcc(*codec_name)
            writer = cv2.VideoWriter(filepath, fourcc, self.fps, (w, h))
            if writer.isOpened():
                print(f"[Recorder] Using codec: {codec_name}, file: {filename}")
                break
            writer.release()
            writer = None

        if writer is None:
            print("[Recorder] ERROR: No working video codec found! Cannot record.")
            return

        # Пишем буфер «до»
        frames_written = 0
        for frame in pre_frames:
            writer.write(frame)
            frames_written += 1

        # Пишем «после» в течение post_seconds
        end_time = time.time() + self.post_seconds
        while time.time() < end_time:
            frame = stream.read()
            if frame is not None:
                writer.write(frame)
                frames_written += 1
            time.sleep(1.0 / self.fps)

        writer.release()
        print(f"[Recorder] Saved incident video: {os.path.basename(filepath)} ({frames_written} frames)")
