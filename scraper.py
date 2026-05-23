"""
Job Board Agent - Scraper ofert pracy
Obsługuje: NoFluffJobs, Pracuj.pl, JustJoinIT
Z obsługą proxy Webshare (rotating residential) + paginacja
"""

import json
import time
import logging
import hashlib
import random
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ============================================================
# KONFIGURACJA
# ============================================================
CONFIG = {
    "keyword": "test",
    "location": "",
    "min_salary": None,
    "output_dir": "output",
    "seen_file": "seen_jobs.json",
    "log_file": "agent.log",
    "delay_between_requests": 2,
    "sources": ["nofluffjobs", "justjoinit", "pracujpl"],
    "max_pages": 20,          # max stron na serwis (20 × 100 = 2000 ofert)
    "stop_on_seen": True,     # zatrzymaj paginację gdy trafisz na już znane oferty
}

# ============================================================
# KONFIGURACJA PROXY (Webshare)
# ============================================================
PROXY = {
    "enabled": True,
    "host": "p.webshare.io",
    "port": 80,
    # ← wstaw tutaj swoje dane z dashboardu Webshare:
    "username": "TWOJ_LOGIN",       # np. fnmfdsyy-pl-19
    "password": "TWOJE_HASLO",      # np. ivpwlsgwnra0
    # Rotating: każdy request dostaje inne IP automatycznie
    # Możesz też użyć kraju: fnmfdsyy-pl-19 = Poland
    # Lub losowe IP:         fnmfdsyy-rotate
}

def get_proxies() -> dict | None:
    """Zwraca dict proxy dla requests lub None gdy wyłączone."""
    if not PROXY["enabled"]:
        return None
    proxy_url = (
        f"http://{PROXY['username']}:{PROXY['password']}"
        f"@{PROXY['host']}:{PROXY['port']}"
    )
    return {"http": proxy_url, "https": proxy_url}

# ============================================================
# HEADERS
# ============================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

def get_headers(extra: dict = None) -> dict:
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept": "application/json, text/html, */*",
    }
    if extra:
        h.update(extra)
    return h

# ============================================================
# LOGGER
# ============================================================
def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(CONFIG["log_file"], encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("job-agent")

log = setup_logger()

# ============================================================
# HELPERS
# ============================================================
def fetch(url, params=None, method="GET", json_body=None, extra_headers=None):
    """HTTP request z proxy, retry i losowym User-Agent."""
    if params and method == "GET":
        url = url + "?" + urllib.parse.urlencode(params)

    proxies = get_proxies()
    headers = get_headers(extra_headers)

    for attempt in range(3):
        try:
            if HAS_REQUESTS:
                if method == "POST":
                    r = requests.post(
                        url, json=json_body, headers=headers,
                        proxies=proxies, timeout=20
                    )
                else:
                    r = requests.get(
                        url, headers=headers,
                        proxies=proxies, timeout=20
                    )
                r.raise_for_status()
                return r
            else:
                # fallback bez proxy (stdlib nie wspiera proxy auth łatwo)
                req = urllib.request.Request(url, headers=headers)
                if method == "POST" and json_body:
                    req.data = json.dumps(json_body).encode()
                    req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    class FR:
                        def __init__(self, d, code):
                            self._d = d
                            self.status_code = code
                        @property
                        def text(self): return self._d.decode("utf-8", errors="replace")
                        def json(self): return json.loads(self._d)
                    return FR(resp.read(), resp.status)
        except Exception as e:
            wait = 2 ** attempt + random.uniform(0, 1)
            log.warning(f"Attempt {attempt+1}/3 failed [{url[:60]}]: {e} — retry za {wait:.1f}s")
            time.sleep(wait)
    log.error(f"Wszystkie próby nieudane: {url[:80]}")
    return None


def job_id(job: dict) -> str:
    key = f"{job.get('source','')}{job.get('url','')}{job.get('title','')}"
    return hashlib.md5(key.encode()).hexdigest()


def load_seen() -> set:
    p = Path(CONFIG["seen_file"])
    if p.exists():
        return set(json.loads(p.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set):
    Path(CONFIG["seen_file"]).write_text(
        json.dumps(list(seen), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_results(jobs: list):
    Path(CONFIG["output_dir"]).mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = Path(CONFIG["output_dir"]) / f"jobs_{date_str}.json"
    existing = []
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    existing.extend(jobs)
    out_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"Zapisano {len(jobs)} nowych ofert → {out_path}")
    return out_path


# ============================================================
# SCRAPERS Z PAGINACJĄ
# ============================================================

def scrape_justjoinit(keyword: str, seen: set) -> list:
    log.info("🔍 JustJoinIT – pobieranie ofert (wszystkie strony)...")
    all_jobs = []
    page = 1
    max_pages = CONFIG["max_pages"]
    extra_h = {"Version": "2"}

    while page <= max_pages:
        log.info(f"  JustJoinIT strona {page}/{max_pages}...")
        resp = fetch(
            "https://api.justjoin.it/v2/user-panel/offers",
            params={"searchTitle": keyword, "page": page, "pageSize": 100, "sortBy": "newest"},
            extra_headers=extra_h,
        )
        if not resp:
            break

        try:
            data = resp.json()
            offers = data.get("data", [])
            if not offers:
                log.info("  JustJoinIT – brak kolejnych ofert")
                break

            new_on_page = 0
            for o in offers:
                salary_ranges = o.get("salaryRanges", [])
                salary = None
                if salary_ranges:
                    s = salary_ranges[0]
                    salary = f"{s.get('from','')}–{s.get('to','')} {s.get('currency','PLN')} ({s.get('employmentType','')})"

                job = {
                    "source": "justjoinit",
                    "title": o.get("title", ""),
                    "company": o.get("companyName", ""),
                    "location": o.get("city", "") or ", ".join(o.get("workplaceType", [])),
                    "remote": o.get("workplaceType", ""),
                    "salary": salary,
                    "technologies": [s.get("name") for s in o.get("requiredSkills", [])],
                    "url": f"https://justjoin.it/offers/{o.get('slug', '')}",
                    "published_at": o.get("publishedAt", ""),
                    "scraped_at": datetime.now().isoformat(),
                }
                jid = job_id(job)
                if jid not in seen:
                    new_on_page += 1
                all_jobs.append(job)

            # Jeśli cała strona to już znane oferty — stop
            if CONFIG["stop_on_seen"] and new_on_page == 0 and page > 1:
                log.info(f"  JustJoinIT – strona {page} to same znane oferty, zatrzymuję")
                break

            meta = data.get("meta", {})
            total_pages = meta.get("totalPages", 1)
            if page >= total_pages:
                break

            page += 1
            time.sleep(CONFIG["delay_between_requests"])

        except Exception as e:
            log.error(f"JustJoinIT strona {page} – błąd: {e}")
            break

    log.info(f"JustJoinIT – łącznie {len(all_jobs)} ofert z {page} stron")
    return all_jobs


def scrape_nofluffjobs(keyword: str, seen: set) -> list:
    log.info("🔍 NoFluffJobs – pobieranie ofert (wszystkie strony)...")
    all_jobs = []
    page = 1
    max_pages = CONFIG["max_pages"]

    while page <= max_pages:
        log.info(f"  NoFluffJobs strona {page}/{max_pages}...")
        resp = fetch(
            "https://nofluffjobs.com/api/search/posting",
            method="POST",
            json_body={
                "criteriaSearch": {"requirement": [keyword]},
                "page": page,
                "pageSize": 100,
                "region": "pl",
            },
        )
        if not resp:
            break

        try:
            data = resp.json()
            postings = data.get("postings", [])
            if not postings:
                log.info("  NoFluffJobs – brak kolejnych ofert")
                break

            new_on_page = 0
            for p in postings:
                salary = None
                sal = p.get("salary")
                if sal:
                    salary = f"{sal.get('from','')}–{sal.get('to','')} {sal.get('currency','PLN')}"

                job = {
                    "source": "nofluffjobs",
                    "title": p.get("title", ""),
                    "company": p.get("name", ""),
                    "location": (
                        p.get("location", {}).get("places", [{}])[0].get("city", "Polska")
                        if p.get("location") else "Polska"
                    ),
                    "remote": p.get("location", {}).get("fullyRemote", False),
                    "salary": salary,
                    "technologies": p.get("technology", []),
                    "url": f"https://nofluffjobs.com/pl/job/{p.get('url', '')}",
                    "published_at": p.get("posted", ""),
                    "scraped_at": datetime.now().isoformat(),
                }
                jid = job_id(job)
                if jid not in seen:
                    new_on_page += 1
                all_jobs.append(job)

            if CONFIG["stop_on_seen"] and new_on_page == 0 and page > 1:
                log.info(f"  NoFluffJobs – strona {page} to same znane oferty, zatrzymuję")
                break

            total = data.get("totalCount", 0)
            if page * 100 >= total:
                break

            page += 1
            time.sleep(CONFIG["delay_between_requests"])

        except Exception as e:
            log.error(f"NoFluffJobs strona {page} – błąd: {e}")
            break

    log.info(f"NoFluffJobs – łącznie {len(all_jobs)} ofert z {page} stron")
    return all_jobs


def scrape_pracujpl(keyword: str, seen: set) -> list:
    log.info("🔍 Pracuj.pl – pobieranie ofert (wszystkie strony)...")
    all_jobs = []
    page = 1
    max_pages = CONFIG["max_pages"]

    while page <= max_pages:
        log.info(f"  Pracuj.pl strona {page}/{max_pages}...")
        resp = fetch(
            "https://massachusetts.pracuj.pl/jobOffers/listing",
            params={"q": keyword, "pn": page},
        )
        if not resp:
            break

        try:
            data = resp.json()
            offers_raw = data.get("groupedOffers", [])
            if not offers_raw:
                log.info("  Pracuj.pl – brak kolejnych ofert")
                break

            new_on_page = 0
            for group in offers_raw:
                for o in group.get("offers", [group]):
                    salary_match = o.get("salaryMatch", {})
                    salary = None
                    if salary_match:
                        salary = (
                            f"{salary_match.get('from','')}–"
                            f"{salary_match.get('to','')} "
                            f"{salary_match.get('currency','PLN')}"
                        )
                    job = {
                        "source": "pracujpl",
                        "title": o.get("jobTitle", ""),
                        "company": o.get("companyName", ""),
                        "location": o.get("jobWorkplace", {}).get("workplaceCityName", ""),
                        "remote": o.get("remoteWork", False),
                        "salary": salary,
                        "technologies": [],
                        "url": o.get("offerAbsoluteUri", ""),
                        "published_at": o.get("lastPublicated", ""),
                        "scraped_at": datetime.now().isoformat(),
                    }
                    jid = job_id(job)
                    if jid not in seen:
                        new_on_page += 1
                    all_jobs.append(job)

            if CONFIG["stop_on_seen"] and new_on_page == 0 and page > 1:
                log.info(f"  Pracuj.pl – strona {page} to same znane oferty, zatrzymuję")
                break

            total_pages = data.get("totalPages", 1)
            if page >= total_pages:
                break

            page += 1
            time.sleep(CONFIG["delay_between_requests"])

        except Exception as e:
            log.error(f"Pracuj.pl strona {page} – błąd: {e}")
            break

    log.info(f"Pracuj.pl – łącznie {len(all_jobs)} ofert z {page} stron")
    return all_jobs


# ============================================================
# FILTROWANIE
# ============================================================
def filter_jobs(jobs: list) -> list:
    filtered = []
    kw = CONFIG["keyword"].lower()
    for j in jobs:
        title_match = kw in j.get("title", "").lower()
        tech_match = any(kw in t.lower() for t in j.get("technologies", []))
        if title_match or tech_match:
            filtered.append(j)
    log.info(f"Po filtracji: {len(filtered)} ofert (było {len(jobs)})")
    return filtered


# ============================================================
# GŁÓWNA LOGIKA
# ============================================================
def run():
    log.info("=" * 60)
    log.info(f"🚀 Agent startuje | keyword='{CONFIG['keyword']}'")
    proxy_status = f"{PROXY['host']}:{PROXY['port']}" if PROXY["enabled"] else "wyłączone"
    log.info(f"🔒 Proxy: {proxy_status}")
    log.info("=" * 60)

    seen = load_seen()
    all_jobs = []
    sources = CONFIG["sources"]
    kw = CONFIG["keyword"]

    if "justjoinit" in sources:
        all_jobs.extend(scrape_justjoinit(kw, seen))
        time.sleep(CONFIG["delay_between_requests"] * 2)

    if "nofluffjobs" in sources:
        all_jobs.extend(scrape_nofluffjobs(kw, seen))
        time.sleep(CONFIG["delay_between_requests"] * 2)

    if "pracujpl" in sources:
        all_jobs.extend(scrape_pracujpl(kw, seen))
        time.sleep(CONFIG["delay_between_requests"] * 2)

    all_jobs = filter_jobs(all_jobs)

    new_jobs = []
    for j in all_jobs:
        jid = job_id(j)
        if jid not in seen:
            j["id"] = jid
            new_jobs.append(j)
            seen.add(jid)

    log.info(f"✅ Nowych ofert: {len(new_jobs)} (łącznie zebranych: {len(all_jobs)})")

    if new_jobs:
        out_path = save_results(new_jobs)
        save_seen(seen)
        log.info(f"📁 Wyniki: {out_path.resolve()}")
    else:
        log.info("ℹ️ Brak nowych ofert do zapisania")

    log.info("=" * 60)
    return new_jobs


if __name__ == "__main__":
    run()
