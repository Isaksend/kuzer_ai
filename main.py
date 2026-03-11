import cv2
import json
import time
import numpy as np
from ultralytics import YOLO
from config import VIDEO_SOURCE, ZONES_FILE, WINDOW_NAME, ALARM_TEXT, ALARM_COLOR, DELAY_SECONDS, MODEL_PATH, CONFIDENCE_THRESHOLD

class ZoneMonitor:
    def __init__(self):
        self.model = YOLO(MODEL_PATH)
        self.zone_polygon = self.load_zone()
        self.alarm_timers = {} # ID: timestamp (last seen in zone)
        
    def load_zone(self):
        try:
            with open(ZONES_FILE, 'r') as f:
                data = json.load(f)
                return np.array(data["zone"], np.int32)
        except (FileNotFoundError, KeyError):
            print(f"Zone file {ZONES_FILE} not found or invalid. Please run zone_selector.py first.")
            return None

    def point_in_polygon(self, point):
        if self.zone_polygon is None:
            return False
        # pt = (x, y)
        result = cv2.pointPolygonTest(self.zone_polygon, point, False)
        return result >= 0

    def draw_zone(self, frame):
        if self.zone_polygon is not None:
            pts = self.zone_polygon.reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
            # Слегка заливаем зону цветом
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], (0, 0, 255))
            cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

    def draw_alarm(self, frame):
        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 3
        thickness = 5
        text_size = cv2.getTextSize(ALARM_TEXT, font, font_scale, thickness)[0]
        text_x = (w - text_size[0]) // 2
        text_y = (h + text_size[1]) // 4
        
        cv2.putText(frame, ALARM_TEXT, (text_x, text_y), font, font_scale, ALARM_COLOR, thickness)

    def run(self):
        if self.zone_polygon is None:
            return

        cap = cv2.VideoCapture(VIDEO_SOURCE)
        if not cap.isOpened():
            print(f"Error opening video stream or file: {VIDEO_SOURCE}")
            return

        print("Running Tracker. Press 'q' to exit.")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            current_time = time.time()
            alarm_active = False

            # YOLO inference with tracking for people only
            results = self.model.track(frame, persist=True, classes=[0], conf=CONFIDENCE_THRESHOLD, verbose=False)
            
            if results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids = results[0].boxes.id.cpu().numpy()
                
                for box, obj_id in zip(boxes, ids):
                    x1, y1, x2, y2 = map(int, box)
                    
                    # Точка входа: нижняя центральная точка (ноги)
                    center_x = (x1 + x2) // 2
                    bottom_y = y2
                    point = (center_x, bottom_y)
                    
                    if self.point_in_polygon(point):
                        self.alarm_timers[obj_id] = current_time
                        
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv2.circle(frame, point, 5, (0, 0, 255), -1)
                        cv2.putText(frame, f"ID: {int(obj_id)}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    else:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                        cv2.circle(frame, point, 5, (255, 0, 0), -1)
                        cv2.putText(frame, f"ID: {int(obj_id)}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            
            # Логика 3 секунд
            ids_to_remove = []
            for obj_id, last_seen_time in self.alarm_timers.items():
                if current_time - last_seen_time <= DELAY_SECONDS:
                    alarm_active = True
                else:
                    ids_to_remove.append(obj_id)
                    
            for obj_id in ids_to_remove:
                del self.alarm_timers[obj_id]
                
            self.draw_zone(frame)
            
            if alarm_active:
                self.draw_alarm(frame)
                
            cv2.imshow(WINDOW_NAME, frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    monitor = ZoneMonitor()
    monitor.run()
