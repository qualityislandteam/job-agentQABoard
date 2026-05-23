"""
Webhook Sender – wysyła nowe oferty do Twojej aplikacji (POST JSON)
Użycie: python send_to_app.py --file output/jobs_2024-01-15.json
        python send_to_app.py --today   (wysyła dzisiejszy plik)
"""

import json
import sys
import argparse
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ============================================================
# KONFIGURACJA WEBHOOKA
# ============================================================
WEBHOOK_URL = "https://twoja-aplikacja.pl/api/jobs"   # ← zmień na swój endpoint
WEBHOOK_SECRET = ""   # opcjonalnie: klucz API / Bearer token
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WEBHOOK] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger()

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def send_jobs(jobs: list, url: str) -> bool:
    """Wysyła listę ofert jako POST JSON do podanego URL."""
    payload = {
        "sent_at": datetime.now().isoformat(),
        "count": len(jobs),
        "jobs": jobs,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "JobAgent/1.0",
    }
    if WEBHOOK_SECRET:
        headers["Authorization"] = f"Bearer {WEBHOOK_SECRET}"

    log.info(f"📤 Wysyłam {len(jobs)} ofert → {url}")

    try:
        if HAS_REQUESTS:
            import requests as req
            r = req.post(url, json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            log.info(f"✅ Sukces! Status: {r.status_code}")
            return True
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=30) as resp:
                log.info(f"✅ Sukces! Status: {resp.status}")
                return True
    except Exception as e:
        log.error(f"❌ Błąd wysyłania: {e}")
        return False


def load_jobs(filepath: str) -> list:
    p = Path(filepath)
    if not p.exists():
        log.error(f"Plik nie istnieje: {p}")
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def get_today_file() -> Path | None:
    date_str = datetime.now().strftime("%Y-%m-%d")
    p = Path("output") / f"jobs_{date_str}.json"
    return p if p.exists() else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wyślij oferty do aplikacji")
    parser.add_argument("--file", help="Ścieżka do pliku JSON z ofertami")
    parser.add_argument("--today", action="store_true", help="Wyślij dzisiejszy plik")
    parser.add_argument("--url", default=WEBHOOK_URL, help="URL webhooka (opcjonalnie)")
    args = parser.parse_args()

    if args.today:
        f = get_today_file()
        if not f:
            log.error("Brak dzisiejszego pliku w output/")
            sys.exit(1)
        jobs = load_jobs(str(f))
    elif args.file:
        jobs = load_jobs(args.file)
    else:
        parser.print_help()
        sys.exit(0)

    if not jobs:
        log.info("Brak ofert do wysłania")
        sys.exit(0)

    success = send_jobs(jobs, args.url)
    sys.exit(0 if success else 1)
