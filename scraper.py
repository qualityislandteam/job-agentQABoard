"""
Job Board Agent - Scraper ofert pracy
Obsługuje: JustJoinIT (kategoria Testing), NoFluffJobs, Pracuj.pl
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

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

CONFIG = {
    "justjoinit_categories": ["testing"],
    "search_keywords": ["tester", "qa", "sdet"],
    "filter_keywords": ["test", "qa", "sdet", "quality", "automation", "manual"],
    "filter_enabled": True,
    "output_dir": "output",
    "seen_file": "seen_jobs.json",
    "log_file": "agent.log",
    "delay_between_requests": 2,
    "sources": ["justjoinit", "nofluffjobs", "pracujpl"],
    "max_pages": 30,
    "stop_on_seen": True,
}

PROXY = {
    "enabled": True,
    "host": "p.webshare.io",
    "port": 80,
    "username": "TWOJ_LOGIN",
    "password": "TWOJE_HASLO",
}

def get_proxies():
    if not PROXY["enabled"]:
        return None
    proxy_url = f"http://{PROXY['username']}:{PROXY['password']}@{PROXY['host']}:{PROXY['port']}"
    return {"http": proxy_url, "https": proxy_url}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def get_headers(extra=None):
    h = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "pl-PL,pl;q=0.9", "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h

def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(CONFIG["log_file"], encoding="utf-8"), logging.StreamHandler()],
    )
    return logging.getLogger("job-agent")

log = setup_logger()

def fetch(url, params=None, method="GET", json_body=None, extra_headers=None):
    if params and method == "GET":
        url = url + "?" + urllib.parse.urlencode(params)
    proxies = get_proxies()
    headers = get_headers(extra_headers)
    for attempt in range(3):
        try:
            if HAS_REQUESTS:
                r = requests.post(url, json=json_body, headers=headers, proxies=proxies, timeout=20) if method == "POST" else requests.get(url, headers=headers, proxies=proxies, timeout=20)
                r.raise_for_status()
                return r
            else:
                req = urllib.request.Request(url, headers=headers)
                if method == "POST" and json_body:
                    req.data = json.dumps(json_body).encode()
                    req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    class FR:
                        def __init__(self, d, c): self._d = d; self.status_code = c
                        def json(self): return json.loads(self._d)
                    return FR(resp.read(), resp.status)
        except Exception as e:
            wait = 2 ** attempt + random.uniform(0, 1)
            log.warning(f"Attempt {attempt+1}/3 failed [{url[:60]}]: {e}")
            time.sleep(wait)
    log.error(f"Wszystkie proby nieudane: {url[:60]}")
    return None

def job_id(job):
    return hashlib.md5(f"{job.get('source','')}{job.get('url','')}{job.get('title','')}".encode()).hexdigest()

def load_seen():
    p = Path(CONFIG["seen_file"])
    return set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()

def save_seen(seen):
    Path(CONFIG["seen_file"]).write_text(json.dumps(list(seen), ensure_ascii=False, indent=2), encoding="utf-8")

def save_results(jobs):
    Path(CONFIG["output_dir"]).mkdir(exist_ok=True)
    out_path = Path(CONFIG["output_dir"]) / f"jobs_{datetime.now().strftime('%Y-%m-%d')}.json"
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
    existing.extend(jobs)
    out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Zapisano {len(jobs)} nowych ofert do {out_path}")
    return out_path

def scrape_justjoinit_category(category, seen):
    log.info(f"JustJoinIT kategoria '{category}'...")
    all_jobs = []
    page = 1
    while page <= CONFIG["max_pages"]:
        log.info(f"  JustJoinIT [{category}] strona {page}...")
        resp = fetch(
            "https://api.justjoin.it/v2/user-panel/offers",
            params={"categories[]": category, "page": page, "pageSize": 100, "sortBy": "newest"},
            extra_headers={"Version": "2"},
        )
        if not resp:
            break
        try:
            data = resp.json()
            offers = data if isinstance(data, list) else data.get("data", [])
            total_pages = 1 if isinstance(data, list) else (data.get("meta", {}) or {}).get("totalPages", 1)
            if not offers:
                break
            new_on_page = 0
            for o in offers:
                if not isinstance(o, dict):
                    continue
                salary = None
                sr_list = o.get("salaryRanges", [])
                if sr_list and isinstance(sr_list[0], dict):
                    sr = sr_list[0]
                    salary = f"{sr.get('from','')}~{sr.get('to','')} {sr.get('currency','PLN')} ({sr.get('employmentType','')})"
                workplace = o.get("workplaceType", [])
                job = {
                    "source": "justjoinit",
                    "title": o.get("title", ""),
                    "company": o.get("companyName", ""),
                    "location": o.get("city", "") or (", ".join(workplace) if isinstance(workplace, list) else ""),
                    "remote": workplace,
                    "salary": salary,
                    "technologies": [sk.get("name","") for sk in o.get("requiredSkills",[]) if isinstance(sk,dict)],
                    "url": f"https://justjoin.it/offers/{o.get('slug','')}",
                    "published_at": o.get("publishedAt", ""),
                    "scraped_at": datetime.now().isoformat(),
                    "category": category,
                }
                if job_id(job) not in seen:
                    new_on_page += 1
                all_jobs.append(job)
            log.info(f"  strona {page}: {len(offers)} ofert, {new_on_page} nowych")
            if CONFIG["stop_on_seen"] and new_on_page == 0 and page > 1:
                log.info("  Same znane oferty, zatrzymuje")
                break
            if page >= total_pages:
                break
            page += 1
            time.sleep(CONFIG["delay_between_requests"])
        except Exception as e:
            import traceback
            log.error(f"JustJoinIT [{category}] strona {page} blad: {e}\n{traceback.format_exc()}")
            break
    log.info(f"JustJoinIT [{category}] lacznie {len(all_jobs)} ofert z {page} stron")
    return all_jobs

def scrape_nofluffjobs(keyword, seen):
    log.info(f"NoFluffJobs '{keyword}'...")
    all_jobs = []
    page = 1
    while page <= CONFIG["max_pages"]:
        resp = None
        for payload in [
            {"criteriaSearch": {"keyword": keyword, "country": "Poland"}, "page": page, "pageSize": 100},
            {"criteriaSearch": {"more": {"keyword": keyword}}, "page": page, "pageSize": 100, "region": "pl"},
        ]:
            r = fetch("https://nofluffjobs.com/api/search/posting", method="POST", json_body=payload)
            if r and r.status_code == 200:
                resp = r
                break
        if not resp:
            log.error(f"NoFluffJobs [{keyword}] blokada")
            break
        try:
            data = resp.json()
            postings = data.get("postings", [])
            if not postings:
                break
            new_on_page = 0
            for p in postings:
                if not isinstance(p, dict):
                    continue
                sal = p.get("salary")
                salary = f"{sal.get('from','')}~{sal.get('to','')} {sal.get('currency','PLN')}" if isinstance(sal, dict) else None
                loc = p.get("location", {})
                places = loc.get("places", []) if isinstance(loc, dict) else []
                location = places[0].get("city", "Polska") if places and isinstance(places[0], dict) else "Polska"
                job = {
                    "source": "nofluffjobs",
                    "title": p.get("title", ""),
                    "company": p.get("name", ""),
                    "location": location,
                    "remote": loc.get("fullyRemote", False) if isinstance(loc, dict) else False,
                    "salary": salary,
                    "technologies": p.get("technology", []),
                    "url": f"https://nofluffjobs.com/pl/job/{p.get('url','')}",
                    "published_at": p.get("posted", ""),
                    "scraped_at": datetime.now().isoformat(),
                }
                if job_id(job) not in seen:
                    new_on_page += 1
                all_jobs.append(job)
            if CONFIG["stop_on_seen"] and new_on_page == 0 and page > 1:
                break
            if page * 100 >= data.get("totalCount", 0):
                break
            page += 1
            time.sleep(CONFIG["delay_between_requests"])
        except Exception as e:
            log.error(f"NoFluffJobs blad: {e}")
            break
    log.info(f"NoFluffJobs [{keyword}] lacznie {len(all_jobs)} ofert")
    return all_jobs

def scrape_pracujpl(keyword, seen):
    log.info(f"Pracuj.pl '{keyword}'...")
    all_jobs = []
    page = 1
    extra = {"Referer": "https://www.pracuj.pl/", "Origin": "https://www.pracuj.pl"}
    while page <= CONFIG["max_pages"]:
        resp = None
        for url in [
            f"https://massachusetts.pracuj.pl/jobOffers/listing?q={urllib.parse.quote(keyword)}&pn={page}",
            f"https://api.pracuj.pl/jobOffers/listing?q={urllib.parse.quote(keyword)}&pn={page}",
        ]:
            r = fetch(url, extra_headers=extra)
            if r and r.status_code == 200:
                resp = r
                break
        if not resp:
            log.error(f"Pracuj.pl [{keyword}] zablokowane")
            break
        try:
            data = resp.json()
            groups = data.get("groupedOffers", data.get("offers", []))
            if not groups:
                break
            new_on_page = 0
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for o in group.get("offers", [group]):
                    if not isinstance(o, dict):
                        continue
                    sm = o.get("salaryMatch", o.get("salary", {}))
                    salary = f"{sm.get('from','')}~{sm.get('to','')} {sm.get('currency','PLN')}" if isinstance(sm, dict) and sm else None
                    wp = o.get("jobWorkplace", {})
                    job = {
                        "source": "pracujpl",
                        "title": o.get("jobTitle", o.get("title", "")),
                        "company": o.get("companyName", ""),
                        "location": wp.get("workplaceCityName", "") if isinstance(wp, dict) else "",
                        "remote": o.get("remoteWork", False),
                        "salary": salary,
                        "technologies": [],
                        "url": o.get("offerAbsoluteUri", o.get("url", "")),
                        "published_at": o.get("lastPublicated", ""),
                        "scraped_at": datetime.now().isoformat(),
                    }
                    if job_id(job) not in seen:
                        new_on_page += 1
                    all_jobs.append(job)
            if CONFIG["stop_on_seen"] and new_on_page == 0 and page > 1:
                break
            if page >= data.get("totalPages", 1):
                break
            page += 1
            time.sleep(CONFIG["delay_between_requests"])
        except Exception as e:
            log.error(f"Pracuj.pl blad: {e}")
            break
    log.info(f"Pracuj.pl [{keyword}] lacznie {len(all_jobs)} ofert")
    return all_jobs

def filter_jobs(jobs):
    if not CONFIG.get("filter_enabled", True):
        return jobs
    keywords = [k.lower() for k in CONFIG.get("filter_keywords", [])]
    if not keywords:
        return jobs
    filtered = [j for j in jobs if any(kw in (j.get("title","")+" "+" ".join(j.get("technologies",[]))).lower() for kw in keywords)]
    log.info(f"Po filtracji: {len(filtered)} ofert (bylo {len(jobs)})")
    return filtered

def run():
    log.info("=" * 60)
    log.info(f"Agent startuje | kategorie JJI: {CONFIG['justjoinit_categories']} | slowa: {CONFIG['search_keywords']}")
    log.info(f"Proxy: {PROXY['host']}:{PROXY['port']}" if PROXY["enabled"] else "Proxy: wylaczone")
    log.info("=" * 60)

    seen = load_seen()
    all_jobs = []

    if "justjoinit" in CONFIG["sources"]:
        for cat in CONFIG["justjoinit_categories"]:
            all_jobs.extend(scrape_justjoinit_category(cat, seen))
            time.sleep(CONFIG["delay_between_requests"] * 2)

    if "nofluffjobs" in CONFIG["sources"]:
        for kw in CONFIG["search_keywords"]:
            all_jobs.extend(scrape_nofluffjobs(kw, seen))
            time.sleep(CONFIG["delay_between_requests"] * 2)

    if "pracujpl" in CONFIG["sources"]:
        for kw in CONFIG["search_keywords"]:
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

    log.info(f"Nowych ofert: {len(new_jobs)} (lacznie zebranych: {len(all_jobs)})")
    if new_jobs:
        save_results(new_jobs)
        save_seen(seen)
    else:
        log.info("Brak nowych ofert")
    log.info("=" * 60)
    return new_jobs

if __name__ == "__main__":
    run()
