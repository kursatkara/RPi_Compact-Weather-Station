#!/usr/bin/env python3
import sqlite3
from datetime import datetime
from pathlib import Path
import csv
import sys

# ======================
# USER CONFIGURATION
# ======================
DB_PATH = Path.home() / "GitRepos" / "RPi_Compact-Weather-Station" / "weather.db"
EXPORT_DIR = Path.home() / "GitRepos" / "RPi_Compact-Weather-Station" / "exports"

# ======================
# HELPER FUNCTIONS
# ======================
def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y/%m/%d")
    except ValueError:
        raise ValueError("Date must be in YYYY/MM/DD format")

# ======================
# MAIN SCRIPT
# ======================
def main():
    print("Weather CSV Export Tool\n")

    try:
        start_input = input("Starting log date [YYYY/MM/DD]: ").strip()
        end_input = input("Ending log date   [YYYY/MM/DD]: ").strip()

        start_date = parse_date(start_input)
        end_date = parse_date(end_input)

        if end_date < start_date:
            raise ValueError("Ending date must be after starting date")

    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # Ensure export directory exists
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = EXPORT_DIR / f"weather_{start_input.replace('/', '-')}_to_{end_input.replace('/', '-')}.csv"

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        query = """
            SELECT timestamp, temp_c, temp_f, pressure_hpa, humidity
            FROM weather
            WHERE timestamp >= ?
              AND timestamp < ?
            ORDER BY timestamp ASC
        """

        cursor.execute(
            query,
            (
                start_date.isoformat(),
                (end_date.replace(hour=23, minute=59, second=59)).isoformat()
            )
        )

        rows = cursor.fetchall()

        if not rows:
            print("[INFO] No data found for the specified date range.")
            sys.exit(0)

        with open(output_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["timestamp", "temp_c", "temp_f", "pressure_hpa", "humidity"])
            writer.writerows(rows)

        conn.close()

        print("[SUCCESS]")
        print(f"Exported {len(rows)} rows")
        print(f"Saved to: {output_file}")

    except Exception as e:
        print(f"[FAILED] Export did not complete: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

