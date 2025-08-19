## Hakilens: Kenya Law Scraper + AI-ready Data Pipeline

This project scaffolds a Python scraper for Kenya Law content (cases and legislation), saves structured data and documents (PDFs/images) to disk + SQL, and provides a CLI to run weekly jobs or on-demand fetches.

### Features
- Scrape a single URL (case detail or listing) and auto-detect what to do
- Crawl listing pages with pagination
- Persist case metadata and text to SQL (SQLite/PostgreSQL)
- Download PDFs/images and store on disk with DB references
- HTML snapshot archive for parser debugging
- Config via environment variables or sensible defaults

### Quickstart
1) Install dependencies
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2) Configure (optional). Defaults store data under `data/` with SQLite. You can set:
- `DATABASE_URL` (e.g. `postgresql+psycopg2://user:pass@localhost:5432/hakilens`)
- `STORAGE_DIR` (default: `<repo>/data`)
- `USER_AGENT` (default: `HakilensScraper/1.0`)
- `REQUESTS_PER_MINUTE` (default: 15)
- `REQUEST_TIMEOUT_SECONDS` (default: 30)

3) Run the CLI
```bash
python -m hakilens_scraper.cli scrape-url https://new.kenyalaw.org/judgments/

# Or crawl a listing with pagination
python -m hakilens_scraper.cli crawl-listing https://new.kenyalaw.org/judgments/
```

4) Where data goes
- DB: SQLite file under `data/hakilens.db` by default (or your configured SQL)
- Files: PDFs/images/HTML under `data/files/`

### Scheduling (weekly)
Use cron (example runs Sundays at 01:00):
```bash
# crontab -e
0 1 * * 0 /bin/bash -lc 'cd /Users/mac/Documents/code/hakilens && source .venv/bin/activate && REQUESTS_PER_MINUTE=15 python -m hakilens_scraper.cli scheduled-run | cat'
```

### Notes on Kenya Law structure
Kenya Law periodically updates layout. The parser saves an HTML snapshot for each processed page under `data/files/html/` to ease selector updates. If fields are missing, adjust selectors in `hakilens_scraper/parsers/kenyalaw.py`.

### AI Pipeline (next steps)
- Chunk and embed case texts (FAISS/Milvus/PGVector)
- Summarize using an LLM (OpenAI/Anthropic/local) and store summaries
- Build a retrieval-augmented API for Q&A

## AI Setup (OpenAI / Azure OpenAI)

Set one of these configurations:

- OpenAI:
```bash
export OPENAI_API_KEY=sk-...
```

- Azure OpenAI:
```bash
export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com"
export AZURE_OPENAI_API_KEY="<azure-key>"
export AZURE_OPENAI_API_VERSION="2024-06-01"
export AZURE_OPENAI_DEPLOYMENT="<deployment-name>" # e.g. gpt-4o-mini
```

## REST API

Start server:
```bash
uvicorn hakilens_scraper.api:app --reload --host 0.0.0.0 --port 8000
```

Open the test page: `http://localhost:8000/`

Open auto-docs: `http://localhost:8000/docs`

## Deployment

### Render
The app is configured for Render deployment with:
- `Procfile`: Uses uvicorn directly for ASGI compatibility
- `app.py`: Root-level entry point
- Environment variables: Set your AI API keys in Render dashboard

### Other Platforms
For other platforms, ensure you're using an ASGI server:
- **Heroku**: Use the Procfile as-is
- **Railway**: Use the Procfile as-is  
- **DigitalOcean App Platform**: Use the Procfile as-is
- **AWS/GCP**: Use uvicorn or gunicorn with uvicorn workers

Endpoints:
- POST `/scrape/url?url=...`
  - Scrapes a case detail page or listing (auto-detects), returns saved case IDs.
  - Deep extraction (AKN + first PDF text) is enabled by default.
- POST `/scrape/listing?url=...&max_pages=5`
  - Crawls a listing with pagination, returns saved case IDs.
  - Deep extraction is enabled by default.
- POST `/scrape/case?url=...`
  - Scrapes a single case detail URL only.
  - Deep extraction is enabled by default.
- GET `/cases?q=...&limit=50&offset=0`
  - Lists cases with optional search.
- GET `/cases/{case_id}`
  - Returns case metadata and text.
- GET `/cases/{case_id}/documents`
  - Lists documents (PDFs) paths for download.
- GET `/cases/{case_id}/images`
  - Lists image paths.
- GET `/files/pdf/{filename}` and `/files/image/{filename}`
  - Serves stored files by filename (from `data/files/pdf` and `data/files/images`).

AI Endpoints:
- POST `/ai/summarize/{case_id}`
  - Summarizes the given case using OpenAI or Azure OpenAI and stores the result in `cases.summary`.
  - Query param `model` (default `gpt-4o-mini` for OpenAI). Azure uses the configured deployment.
- POST `/ai/ask`
  - Body: `{ "q": "your legal question" }`
  - Naive keyword retrieval over `title` and `content_text`, then LLM answers using only retrieved context. Returns `answer` and `used_cases`.
 - POST `/ai/chat/{case_id}`
   - Body: `{ "q": "question about this case" }`
   - Chats using only the specified case’s stored content (metadata + text). Uses your Azure/OpenAI configuration. Returns `{ "answer": "..." }`.

## Sample HTML
A simple tester is provided at `static/index.html` and served at `/` by the API. Deep extraction is always on in the UI. In the case detail panel there’s a chat box that calls `/ai/chat/{case_id}`.


