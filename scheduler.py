"""
Scheduler – uruchamia job scraper codziennie o 8:00
Użycie: python scheduler.py
"""

import time
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RUN_HOUR = 8       # godzina uruchomienia
RUN_MINUTE = 0     # minuta uruchomienia
CHECK_INTERVAL = 60  # sprawdzaj co 60 sekund

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(message)s",
    handlers=[
        logging.FileHandler("scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger()

last_run_date = None


def should_run_now() -> bool:
    global last_run_date
    now = datetime.now()
    today = now.date()
    if now.hour == RUN_HOUR and now.minute == RUN_MINUTE:
        if last_run_date != today:
            return True
    return False


def run_scraper():
    global last_run_date
    log.info("▶️  Uruchamiam scraper...")
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "scraper.py")],
            capture_output=True, text=True, timeout=300
        )
        if result.stdout:
            log.info(result.stdout.strip())
        if result.stderr:
            log.warning(result.stderr.strip())
        last_run_date = datetime.now().date()
        log.info("✅ Scraper zakończony pomyślnie")
    except subprocess.TimeoutExpired:
        log.error("❌ Scraper przekroczył limit czasu (5 min)")
    except Exception as e:
        log.error(f"❌ Błąd uruchamiania scrapera: {e}")


if __name__ == "__main__":
    log.info(f"⏰ Scheduler uruchomiony | Codziennie o {RUN_HOUR:02d}:{RUN_MINUTE:02d}")
    log.info("   Ctrl+C żeby zatrzymać\n")

    while True:
        if should_run_now():
            run_scraper()
        else:
            now = datetime.now()
            log.debug(f"Czekam... teraz {now.strftime('%H:%M')}, uruchomię o {RUN_HOUR:02d}:{RUN_MINUTE:02d}")
        time.sleep(CHECK_INTERVAL)
