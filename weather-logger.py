#!/usr/bin/env python3
import os
import time
import socket
import tarfile
import shutil
from datetime import datetime, timedelta

import board
import busio
import adafruit_bme280.basic as bme280
from pathlib import Path
import subprocess

# ----------------------
# CONFIGURATION
# ----------------------
LOG_BASE = Path.home() / "RPi_Compact-Weather-Station" / "logs"
LOG_INTERVAL = 60               # seconds between sensor reads
GIT_PUSH_INTERVAL_MINUTES = 30  # push at every :00 and :30
ARCHIVE_DAYS = 30
CSV_HEADER = "temp_c,temp_f,pressure_hpa,humidity"

# ----------------------
# INITIALIZE SENSOR
# ----------------------
i2c = busio.I2C(board.SCL, board.SDA)
sensor = bme280.Adafruit_BME280_I2C(i2c, address=0x76)
sensor.sea_level_pressure = 1013.25

# ----------------------
# HELPER FUNCTIONS
# ----------------------
def is_online(host="github.com", port=443, timeout=5):
    try:
        socket.create_connection((host, port), timeout=timeout)
        return True
    except OSError:
        return False

def ensure_log_file(path: Path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(CSV_HEADER + "\n")

def get_log_path() -> Path:
    now = datetime.now()
    year = str(now.year)
    month = now.strftime("%m_%B")
    week = f"Week_{now.isocalendar()[1]:02d}"
    filename = now.strftime("%Y-%m-%d.log")
    return LOG_BASE / year / month / week / filename

def log_alert(message: str):
    now = datetime.now()
    year = str(now.year)
    month = now.strftime("%m_%B")
    week = f"Week_{now.isocalendar()[1]:02d}"
    folder = LOG_BASE / year / month / week
    folder.mkdir(parents=True, exist_ok=True)
    alert_file = folder / "ALERTS.log"
    timestamp = now.isoformat(timespec="seconds")
    with open(alert_file, "a") as f:
        f.write(f"{timestamp} {message}\n")
    print(f"[ALERT] {message}")

def log_data(logfile: Path, line: str):
    timestamp = datetime.now().isoformat(timespec="seconds")
    with open(logfile, "a") as f:
        f.write(f"{timestamp} {line}\n")
    log_alert(f"[DATA LOGGED] {line}")

def push_git():
    now = datetime.now()
    if not is_online():
        log_alert(f"[GIT PUSH SKIPPED] Offline. Will retry at next interval ({now.strftime('%Y-%m-%d %H:%M')})")
        return
    try:
        subprocess.run(["git", "-C", str(LOG_BASE.parent), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(LOG_BASE.parent),
            "commit", "-m",
            f"Automated log update {now.strftime('%Y-%m-%d %H:%M')}"
        ], check=True)
        subprocess.run(["git", "-C", str(LOG_BASE.parent), "push"], check=True)
        log_alert(f"[GIT PUSH] Successful at {now.strftime('%Y-%m-%d %H:%M')}")
    except subprocess.CalledProcessError as e:
        log_alert(f"[GIT PUSH ERROR] {e}. Will retry next interval.")

def compress_old_weeks():
    cutoff = datetime.now() - timedelta(days=ARCHIVE_DAYS)
    for year_dir in LOG_BASE.iterdir():
        if not year_dir.is_dir():
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
            for week_dir in month_dir.iterdir():
                if not week_dir.is_dir():
                    continue
                log_files = sorted([f for f in week_dir.iterdir() if f.suffix == ".log"])
                if not log_files:
                    continue
                last_log_file = log_files[-1]
                try:
                    last_log_date = datetime.strptime(last_log_file.stem, "%Y-%m-%d")
                except ValueError:
                    continue
                if last_log_date < cutoff:
                    archive_name = str(week_dir) + ".tar.gz"
                    with tarfile.open(archive_name, "w:gz") as tar:
                        for f in week_dir.iterdir():
                            tar.add(f, arcname=f.name)
                    shutil.rmtree(week_dir)
                    log_alert(f"[ARCHIVE] Compressed week folder {week_dir} -> {archive_name}")

# ----------------------
# MAIN LOOP
# ----------------------
log_alert("Weather logger started... Press Ctrl+C to stop.")

last_git_push_time = None
next_push = lambda: (datetime.now().replace(minute=(0 if datetime.now().minute < 30 else 30),
                                             second=0, microsecond=0))
log_alert(f"Next Git push scheduled at: {next_push().strftime('%Y-%m-%d %H:%M')}")

try:
    last_log_monotonic = time.monotonic()

    while True:
        # ----------------------
        # Sensor read & log
        # ----------------------
        now_monotonic = time.monotonic()
        if now_monotonic - last_log_monotonic >= LOG_INTERVAL:
            last_log_monotonic = now_monotonic
            logfile = get_log_path()
            ensure_log_file(logfile)

            temp_c = round(sensor.temperature, 2)
            temp_f = round(temp_c * 1.8 + 32, 2)
            pressure = round(sensor.pressure, 2)
            humidity = round(sensor.humidity, 2)
            line = f"{temp_c},{temp_f},{pressure},{humidity}"
            log_data(logfile, line)

        # ----------------------
        # Compress old weeks
        # ----------------------
        compress_old_weeks()

        # ----------------------
        # Git push every :00/:30
        # ----------------------
        now = datetime.now()
        interval_id = now.strftime("%Y-%m-%d_%H_%M")
        if now.minute % 30 == 0 and interval_id != last_git_push_time:
            last_git_push_time = interval_id
            push_git()

        # ----------------------
        # Sleep small interval for efficiency
        # ----------------------
        time.sleep(1)

except KeyboardInterrupt:
    log_alert("Logger stopped by user.")

