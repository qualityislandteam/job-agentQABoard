# 🤖 Job Board Agent

Automatyczny scraper ofert pracy z NoFluffJobs, JustJoin.IT i Pracuj.pl.
Codziennie o 8:00 pobiera nowe oferty, deduplikuje je i zapisuje do JSON.

---

## 📁 Struktura plików

```
job-agent/
├── scraper.py        # Główny scraper (logika pobierania)
├── scheduler.py      # Uruchamia scraper codziennie o 8:00
├── send_to_app.py    # Wysyła wyniki do Twojej aplikacji (webhook)
├── requirements.txt  # Zależności Python
├── output/           # Wyniki (tworzone automatycznie)
│   └── jobs_YYYY-MM-DD.json
├── seen_jobs.json    # Cache widzianych ofert (deduplikacja)
└── agent.log         # Logi
```

---

## ⚙️ Instalacja

### 1. Wymagania
- Python 3.9+
- (opcjonalnie) pip

### 2. Zainstaluj zależności
```bash
pip install -r requirements.txt
```
> Bez `requests` i `beautifulsoup4` agent działa na bibliotekach standardowych,
> ale z nimi działa szybciej i jest bardziej odporny.

---

## 🚀 Uruchomienie

### Jednorazowy test
```bash
python scraper.py
```

### Scheduler (działa cały czas w tle, odpala o 8:00)
```bash
python scheduler.py
```

### Wyślij wyniki do aplikacji
```bash
# Dzisiejszy plik:
python send_to_app.py --today

# Konkretny plik:
python send_to_app.py --file output/jobs_2024-01-15.json

# Inny endpoint:
python send_to_app.py --today --url https://moja-app.pl/api/jobs
```

---

## ⏰ Alternatywa: cron (Linux/Mac)

Zamiast `scheduler.py` możesz dodać zadanie do crontab:
```bash
crontab -e
```
Dodaj linię (uruchomienie o 8:00 każdego dnia):
```
0 8 * * * /usr/bin/python3 /ścieżka/do/job-agent/scraper.py
```

### Windows Task Scheduler
1. Otwórz "Harmonogram zadań"
2. Utwórz zadanie → Wyzwalacz: codziennie o 8:00
3. Akcja: `python C:\ścieżka\job-agent\scraper.py`

---

## 🔧 Konfiguracja (scraper.py)

W pliku `scraper.py` znajdź sekcję `CONFIG` i dostosuj:

```python
CONFIG = {
    "keyword": "test",         # ← słowo kluczowe wyszukiwania
    "location": "",            # ← np. "Warszawa" lub "" (cała Polska)
    "min_salary": None,        # ← np. 10000 lub None
    "output_dir": "output",
    "delay_between_requests": 2,
    "sources": ["nofluffjobs", "justjoinit", "pracujpl"],
}
```

---

## 📦 Format wyjściowy JSON

Każda oferta zawiera:
```json
{
  "id": "abc123...",
  "source": "justjoinit",
  "title": "QA Tester",
  "company": "Firma Sp. z o.o.",
  "location": "Warszawa",
  "remote": true,
  "salary": "8000–12000 PLN (B2B)",
  "technologies": ["Selenium", "Cypress", "JIRA"],
  "url": "https://justjoin.it/offers/...",
  "published_at": "2024-01-15T10:00:00",
  "scraped_at": "2024-01-15T08:01:23"
}
```

---

## 🔗 Integracja z aplikacją (webhook)

W `send_to_app.py` ustaw:
```python
WEBHOOK_URL = "https://twoja-aplikacja.pl/api/jobs"
WEBHOOK_SECRET = "twój-klucz-api"  # opcjonalnie
```

Agent wyśle POST z payloadem:
```json
{
  "sent_at": "2024-01-15T08:01:30",
  "count": 42,
  "jobs": [ ... ]
}
```

---

## ⚠️ Uwagi

- Agent szanuje serwery (2 sekundy przerwy między requestami)
- Deduplikacja działa między uruchomieniami (plik `seen_jobs.json`)
- API serwisów mogą się zmieniać – w razie błędów sprawdź logi (`agent.log`)
- Scraping może naruszać ToS niektórych serwisów – używaj odpowiedzialnie
