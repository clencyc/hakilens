from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
import traceback
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi import Body
from openai import OpenAI
from .config import settings as _llm_settings
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Case, Document, Image, get_session, init_db
from .scraper import scrape_url, crawl_listing, scrape_case_detail, search_and_scrape


app = FastAPI(title="Hakilens Scraper API", version="0.1.0")

# CORS
_cors_origins = [
	"http://localhost",
	"http://localhost:3000",
	"http://localhost:8000",
	"http://127.0.0.1:3000",
	"http://127.0.0.1:8000",
	"https://f9e4cc818023.ngrok-free.app",
	"http://f9e4cc818023.ngrok-free.app",
]
app.add_middleware(
	CORSMiddleware,
	allow_origins=_cors_origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Accept alternate base path used by some deployments/clients: /api/hakilens
@app.middleware("http")
async def strip_alt_prefix(request, call_next):
	prefix = "/api/hakilens"
	path = request.url.path
	if path.startswith(prefix):
		new_path = path[len(prefix):] or "/"
		request.scope["path"] = new_path
	return await call_next(request)


@app.on_event("startup")
def startup_event() -> None:
	init_db()


@app.get("/health")
def health() -> dict[str, str]:
	return {"status": "ok"}


@app.post("/scrape/url")
def api_scrape_url(
	url: str = Query(..., description="Case detail or listing URL"),
	deep: bool = Query(True, description="Enable deeper extraction (AKN/PDF text)"),
) -> dict[str, Any]:
	try:
		if not (url.startswith("http://") or url.startswith("https://")):
			raise HTTPException(status_code=400, detail="Invalid url. Must start with http(s)://")
		ids = scrape_url(url, deep=deep)
		return {"saved_case_ids": ids}
	except Exception as e:
		print("/scrape/url error:\n" + traceback.format_exc())
		raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape/listing")
def api_crawl_listing(url: str, max_pages: int | None = None, deep: bool = True) -> dict[str, Any]:
	try:
		ids = crawl_listing(url, max_pages=max_pages, deep=deep)
		return {"saved_case_ids": ids}
	except Exception as e:
		print("/scrape/listing error:\n" + traceback.format_exc())
		raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape/case")
def api_scrape_case(url: str, deep: bool = True) -> dict[str, Any]:
	try:
		if not (url.startswith("http://") or url.startswith("https://")):
			raise HTTPException(status_code=400, detail="Invalid url. Must start with http(s)://")
		cid = scrape_case_detail(url, deep=deep)
		return {"saved_case_id": cid}
	except Exception as e:
		print("/scrape/case error:\n" + traceback.format_exc())
		raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape/search")
def api_scrape_search(q: str = Query(..., description="Case number or keywords"), deep: bool = True) -> dict[str, Any]:
	try:
		ids = search_and_scrape(q, deep=deep)
		return {"saved_case_ids": ids, "query": q}
	except Exception as e:
		print("/scrape/search error:\n" + traceback.format_exc())
		raise HTTPException(status_code=500, detail=str(e))


@app.get("/cases")
def list_cases(q: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
	with get_session() as session:
		query = session.query(Case).order_by(Case.id.desc())
		if q:
			pattern = f"%{q}%"
			query = query.filter(
				(Case.title.ilike(pattern))
				| (Case.case_number.ilike(pattern))
				| (Case.court.ilike(pattern))
				| (Case.citation.ilike(pattern))
			)
		total = query.count()
		rows = query.limit(limit).offset(offset).all()
		return {
			"total": total,
			"items": [
				{
					"id": c.id,
					"url": c.url,
					"title": c.title,
					"case_number": c.case_number,
					"court": c.court,
					"date": c.date,
					"citation": c.citation,
				}
				for c in rows
			],
		}


@app.get("/cases/{case_id}")
def get_case(case_id: int) -> dict[str, Any]:
	with get_session() as session:
		c = session.get(Case, case_id)
		if not c:
			raise HTTPException(status_code=404, detail="case not found")
		return {
			"id": c.id,
			"url": c.url,
			"title": c.title,
			"case_number": c.case_number,
			"court": c.court,
			"parties": c.parties,
			"judges": c.judges,
			"date": c.date,
			"citation": c.citation,
			"summary": c.summary,
			"content_text": c.content_text,
		}


# --- AI endpoints (summaries and RAG-style prompt over DB) ---

@app.post("/ai/summarize/{case_id}")
def summarize_case(case_id: int, model: str = Query("gpt-4o-mini")) -> dict[str, Any]:
	with get_session() as session:
		c = session.get(Case, case_id)
		if not c:
			raise HTTPException(status_code=404, detail="case not found")
		text = c.content_text or c.title or c.citation or ""
		if not text:
			raise HTTPException(status_code=400, detail="no content to summarize")

		# Support Azure OpenAI or vanilla OpenAI
		if _llm_settings.azure_openai_endpoint and _llm_settings.azure_openai_api_key:
			client = OpenAI(
				api_key=_llm_settings.azure_openai_api_key,
				base_url=f"{_llm_settings.azure_openai_endpoint}/openai/deployments/{_llm_settings.azure_openai_deployment}",
				default_query={"api-version": _llm_settings.azure_openai_api_version},
			)
			use_model = "gpt-4o-mini"
		elif _llm_settings.openai_api_key:
			client = OpenAI(api_key=_llm_settings.openai_api_key)
			use_model = model
		else:
			raise HTTPException(status_code=500, detail="LLM not configured. Set Azure or OpenAI keys in config/env.")

		prompt = f"Summarize this Kenyan case for a lawyer. Include facts, issues, holding, and outcome in 5-8 bullets.\n\n{text[:20000]}"
		resp = client.chat.completions.create(
			model=use_model,
			messages=[
				{"role": "system", "content": "You are a concise legal assistant for Kenyan case law."},
				{"role": "user", "content": prompt},
			],
			temperature=0.2,
		)
		summary = resp.choices[0].message.content.strip()
		c.summary = summary
		from .db import db_write_lock
		with db_write_lock:
			session.flush()
		return {"case_id": c.id, "summary": summary}



@app.post("/ai/ask")
def ask_ai(q: str = Body(..., embed=True), model: str = Query("gpt-4o-mini"), k: int = Query(5)) -> dict[str, Any]:
	"""Simple DB keyword retrieval + LLM answer (starter RAG)."""

	with get_session() as session:
		# naive keyword search across title/content
		pattern = f"%{q}%"
		rows = (
			session.query(Case)
			.filter((Case.title.ilike(pattern)) | (Case.content_text.ilike(pattern)))
			.order_by(Case.id.desc())
			.limit(k)
			.all()
		)
		contexts = []
		for c in rows:
			ctx = f"Title: {c.title}\nCase No: {c.case_number}\nCourt: {c.court}\nDate: {c.date}\nExcerpt:\n{(c.content_text or '')[:4000]}"
			contexts.append(ctx)

		if _llm_settings.azure_openai_endpoint and _llm_settings.azure_openai_api_key:
			client = OpenAI(
				api_key=_llm_settings.azure_openai_api_key,
				base_url=f"{_llm_settings.azure_openai_endpoint}/openai/deployments/{_llm_settings.azure_openai_deployment}",
				default_query={"api-version": _llm_settings.azure_openai_api_version},
			)
			use_model = "gpt-4o-mini"
		elif _llm_settings.openai_api_key:
			client = OpenAI(api_key=_llm_settings.openai_api_key)
			use_model = model
		else:
			raise HTTPException(status_code=500, detail="LLM not configured. Set Azure or OpenAI keys in config/env.")
		prompt = (
			"You are a Kenyan legal research assistant. Use only the provided context to answer. "
			"Cite titles of cases you used. If unsure, say you don't know.\n\n" +
			"\n\n".join(contexts) +
			f"\n\nQuestion: {q}\nAnswer:"
		)
		resp = client.chat.completions.create(
			model=use_model,
			messages=[
				{"role": "system", "content": "You answer using provided legal context only."},
				{"role": "user", "content": prompt},
			],
			temperature=0.2,
		)
		answer = resp.choices[0].message.content.strip()
		return {"answer": answer, "used_cases": [c.id for c in rows]}


@app.post("/ai/chat/{case_id}")
def chat_with_case(case_id: int, q: str = Body(..., embed=True), model: str = Query("gpt-4o-mini")) -> dict[str, Any]:
	"""Chat about a single case using its stored content and metadata."""
	with get_session() as session:
		c = session.get(Case, case_id)
		if not c:
			raise HTTPException(status_code=404, detail="case not found")
		context = (
			f"Title: {c.title}\nCase No: {c.case_number}\nCourt: {c.court}\nDate: {c.date}\nCitation: {c.citation}\n\n"
			+ (c.content_text or "")[:12000]
		)
		if _llm_settings.azure_openai_endpoint and _llm_settings.azure_openai_api_key:
			client = OpenAI(
				api_key=_llm_settings.azure_openai_api_key,
				base_url=f"{_llm_settings.azure_openai_endpoint}/openai/deployments/{_llm_settings.azure_openai_deployment}",
				default_query={"api-version": _llm_settings.azure_openai_api_version},
			)
			use_model = "gpt-4o-mini"
		elif _llm_settings.openai_api_key:
			client = OpenAI(api_key=_llm_settings.openai_api_key)
			use_model = model
		else:
			raise HTTPException(status_code=500, detail="LLM not configured. Set Azure or OpenAI keys in config/env.")
		prompt = (
			"You are a Kenyan legal assistant. Answer based only on the case content below."
			" Provide precise, cited references to sections where possible. If unsure, say you don't know.\n\n"
			+ context + f"\n\nUser: {q}\nAnswer:"
		)
		resp = client.chat.completions.create(
			model=use_model,
			messages=[
				{"role": "system", "content": "You answer using the provided single-case context only."},
				{"role": "user", "content": prompt},
			],
			temperature=0.2,
		)
		answer = resp.choices[0].message.content.strip()
		return {"answer": answer}


@app.get("/cases/{case_id}/documents")
def list_case_documents(case_id: int) -> dict[str, Any]:
	with get_session() as session:
		c = session.get(Case, case_id)
		if not c:
			raise HTTPException(status_code=404, detail="case not found")
		rows = session.query(Document).filter(Document.case_id == case_id).order_by(Document.id).all()
		return {
			"items": [
				{"id": d.id, "url": d.url, "file_path": d.file_path, "content_type": d.content_type}
				for d in rows
			]
		}


@app.get("/cases/{case_id}/images")
def list_case_images(case_id: int) -> dict[str, Any]:
	with get_session() as session:
		c = session.get(Case, case_id)
		if not c:
			raise HTTPException(status_code=404, detail="case not found")
		rows = session.query(Image).filter(Image.case_id == case_id).order_by(Image.id).all()
		return {"items": [{"id": i.id, "url": i.url, "file_path": i.file_path} for i in rows]}


@app.get("/files/pdf/{filename}")
def serve_pdf(filename: str):
	path = Path(settings.pdf_dir) / filename
	if not path.exists():
		raise HTTPException(status_code=404, detail="file not found")
	return FileResponse(path)


@app.get("/files/image/{filename}")
def serve_image(filename: str):
	path = Path(settings.image_dir) / filename
	if not path.exists():
		raise HTTPException(status_code=404, detail="file not found")
	return FileResponse(path)


@app.get("/")
def index() -> HTMLResponse:
	html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
	return HTMLResponse(content=html)


