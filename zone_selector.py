import cv2
import json
import numpy as np
from config import VIDEO_SOURCE, ZONES_FILE, WINDOW_NAME, ZONE_COLORS


class ZoneSelector:
    """Позволяет задать несколько запрещённых зон на первом кадре видео."""

    def __init__(self, video_source=VIDEO_SOURCE, zones_file=ZONES_FILE):
        self.video_source = video_source
        self.zones_file = zones_file
        self.zones = []          # Список завершённых зон [{"name": ..., "points": [...]}]
        self.current_points = [] # Точки текущего рисуемого полигона
        self.frame = None
        self.window_name = WINDOW_NAME

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.current_points.append((x, y))
            self._redraw()

    def _redraw(self):
        """Перерисовывает все завершённые зоны и текущий рисуемый полигон."""
        temp = self.frame.copy()

        # Рисуем уже сохранённые зоны
        for i, zone in enumerate(self.zones):
            color = ZONE_COLORS[i % len(ZONE_COLORS)]
            pts = np.array(zone["points"], np.int32).reshape((-1, 1, 2))
            cv2.polylines(temp, [pts], isClosed=True, color=color, thickness=2)
            overlay = temp.copy()
            cv2.fillPoly(overlay, [pts], color)
            cv2.addWeighted(overlay, 0.20, temp, 0.80, 0, temp)
            # Имя зоны
            cx = int(np.mean([p[0] for p in zone["points"]]))
            cy = int(np.mean([p[1] for p in zone["points"]]))
            cv2.putText(temp, zone["name"], (cx - 30, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Рисуем текущий незавершённый полигон
        if len(self.current_points) > 1:
            pts = np.array(self.current_points, np.int32).reshape((-1, 1, 2))
            cv2.polylines(temp, [pts], isClosed=False, color=(0, 255, 0), thickness=2)

        for pt in self.current_points:
            cv2.circle(temp, pt, 5, (0, 255, 0), -1)

        # Подсказки
        h = temp.shape[0]
        help_lines = [
            "LMB: add point | Enter/Space: finish zone",
            "C: clear current | S: save all & exit",
        ]
        for j, line in enumerate(help_lines):
            cv2.putText(temp, line, (10, h - 20 - j * 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow(self.window_name, temp)

    def _finish_current_zone(self):
        """Завершает текущий полигон и добавляет его в список зон."""
        if len(self.current_points) < 3:
            print("Need at least 3 points for a zone. Keep clicking.")
            return
        zone_index = len(self.zones) + 1
        name = f"Zone_{zone_index}"
        self.zones.append({"name": name, "points": self.current_points[:]})
        print(f"  -> '{name}' saved with {len(self.current_points)} points.")
        self.current_points = []
        self._redraw()

    def select_zones(self):
        """Основной цикл разметки. Возвращает True если хотя бы одна зона создана."""
        cap = cv2.VideoCapture(self.video_source)
        if not cap.isOpened():
            print(f"Error opening video: {self.video_source}")
            return False

        ret, self.frame = cap.read()
        cap.release()
        if not ret:
            print("Can't read first frame.")
            return False

        cv2.imshow(self.window_name, self.frame)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)

        print("=== Zone Selector (Multi-Zone) ===")
        print("  LMB        — добавить точку")
        print("  Enter/Space — завершить текущую зону и начать следующую")
        print("  C          — очистить текущий полигон")
        print("  S          — сохранить все зоны в файл и выйти")

        try:
            while True:
                key = cv2.waitKey(1) & 0xFF

                if key in [13, 32]:  # Enter / Space — завершить текущую зону
                    self._finish_current_zone()

                elif key == ord('c'):  # Очистить текущий рисуемый полигон
                    self.current_points = []
                    self._redraw()

                elif key == ord('s'):  # Сохранить всё и выйти
                    self._finish_current_zone()  # На случай если есть незавершённая зона
                    break

                if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                    self._finish_current_zone()
                    break
        except KeyboardInterrupt:
            self._finish_current_zone()

        cv2.destroyAllWindows()
        return self._save()

    def _save(self):
        """Сохраняет все зоны в JSON."""
        if not self.zones:
            print("No zones created. Nothing saved.")
            return False

        with open(self.zones_file, 'w', encoding='utf-8') as f:
            json.dump({"zones": self.zones}, f, indent=4, ensure_ascii=False)

        print(f"\nSaved {len(self.zones)} zone(s) to {self.zones_file}.")
        return True


if __name__ == "__main__":
    selector = ZoneSelector()
    selector.select_zones()
