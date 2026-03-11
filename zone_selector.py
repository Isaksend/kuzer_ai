import cv2
import json
import numpy as np
from config import VIDEO_SOURCE, ZONES_FILE, WINDOW_NAME

class ZoneSelector:
    def __init__(self, video_source=VIDEO_SOURCE, zones_file=ZONES_FILE):
        self.video_source = video_source
        self.zones_file = zones_file
        self.points = []
        self.frame = None
        self.window_name = WINDOW_NAME

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.points.append((x, y))
            self.draw_polygon()

    def draw_polygon(self):
        temp_frame = self.frame.copy()
        if len(self.points) > 1:
            pts = np.array(self.points, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(temp_frame, [pts], isClosed=False, color=(0, 255, 0), thickness=2)
        
        for pt in self.points:
            cv2.circle(temp_frame, pt, 5, (0, 0, 255), -1)
            
        cv2.imshow(self.window_name, temp_frame)

    def select_zone(self):
        cap = cv2.VideoCapture(self.video_source)
        if not cap.isOpened():
            print(f"Error opening video stream or file: {self.video_source}")
            return False

        ret, self.frame = cap.read()
        cap.release()

        if not ret:
            print("Can't receive first frame (stream end?). Exiting ...")
            return False

        cv2.imshow(self.window_name, self.frame)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)

        print("Click to add points. Press 'c' to clear. Press 'Enter' or 'Space' to save and exit.")

        try:
            while True:
                key = cv2.waitKey(1) & 0xFF
                if key in [13, 32]: # Enter or Space
                    break
                elif key == ord('c'):
                    self.points = []
                    cv2.imshow(self.window_name, self.frame)
                
                # Если пользователь нажал крестик (закрыл окно)
                if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
        except KeyboardInterrupt:
            # Перехватываем Ctrl+C в терминале
            pass

        cv2.destroyAllWindows()
        self.save_zone()
        return True

    def save_zone(self):
        if len(self.points) > 2:
            with open(self.zones_file, 'w') as f:
                json.dump({"zone": self.points}, f, indent=4)
            print(f"Zone saved to {self.zones_file} with {len(self.points)} points.")
            return True
        else:
            print("Not enough points to form a polygon. Needs at least 3 points.")
            return False

if __name__ == "__main__":
    selector = ZoneSelector()
    selector.select_zone()
