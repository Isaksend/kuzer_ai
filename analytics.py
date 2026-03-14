import csv
import os
from collections import defaultdict
from datetime import datetime
from config import LOG_FILE


class Analytics:
    """Генерирует аналитику из CSV-лога инцидентов."""

    @staticmethod
    def load_incidents():
        if not os.path.exists(LOG_FILE):
            return []
        rows = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    @classmethod
    def generate_report(cls):
        rows = cls.load_incidents()
        if not rows:
            return {
                "total_incidents": 0,
                "unique_ids": 0,
                "zones": {},
                "hourly": {},
                "top_offenders": [],
            }

        # Подсчёты
        zone_counts = defaultdict(int)
        hourly_counts = defaultdict(int)
        id_counts = defaultdict(int)
        unique_ids = set()

        for row in rows:
            zone_name = row.get("zone_name", "Unknown")
            obj_id = row.get("object_id", "?")
            timestamp_str = row.get("timestamp", "")

            zone_counts[zone_name] += 1
            id_counts[obj_id] += 1
            unique_ids.add(obj_id)

            # Час из timestamp (формат: 2026-03-12_06-17-37)
            try:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
                hourly_counts[dt.strftime("%H:00")] += 1
            except ValueError:
                pass

        # Топ нарушителей
        top = sorted(id_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_incidents": len(rows),
            "unique_ids": len(unique_ids),
            "zones": dict(zone_counts),
            "hourly": dict(sorted(hourly_counts.items())),
            "top_offenders": [{"id": k, "count": v} for k, v in top],
        }
