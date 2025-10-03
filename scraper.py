from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .db import Case, Document, Image, get_session, init_db
from .http_utils import http_client
from .storage import save_html_snapshot, save_image, save_pdf, save_xml
from .parsers.kenyalaw import is_listing_page, extract_listing_links, parse_case_detail
from .akn import extract_plain_text_from_akn
from pypdf import PdfReader
from sqlalchemy.exc import IntegrityError, OperationalError
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
import threading


def normalize_url(base: str, href: str) -> str:
	return urljoin(base, href)


_transaction_lock = threading.RLock()

@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=2))
def scrape_case_detail(url: str, deep: bool = False) -> int:
	resp = http_client.get(url)
	save_html_snapshot(resp.url, resp.text)
	parsed = parse_case_detail(resp.url, resp.text)

	init_db()
	# Serialize the entire DB transaction to avoid SQLite write contention
	with _transaction_lock, get_session() as session:
		existing = session.query(Case).filter(Case.url == parsed.url).one_or_none()
		if existing:
			case = existing
		else:
			case = Case(url=parsed.url)
			session.add(case)
			from .db import db_write_lock
			with db_write_lock:
				try:
					session.flush()
				except IntegrityError:
					# Another concurrent request inserted the same URL; fetch it
					session.rollback()
					case = session.query(Case).filter(Case.url == parsed.url).one()
				except OperationalError:
					# SQLite locked, let retry handle
					session.rollback()
					raise

		case.title = parsed.title
		case.case_number = parsed.case_number
		case.court = parsed.court
		case.parties = parsed.parties
		case.judges = parsed.judges
		case.date = parsed.date
		case.citation = parsed.citation
		case.content_text = parsed.content_text
		from .db import db_write_lock
		with db_write_lock:
			try:
				session.flush()
				session.commit()
			except OperationalError:
				session.rollback()
				raise

		# Attempt Akoma Ntoso XML if discoverable by replacing /eng@ with plausible XML paths
		try:
			if "/eng@" in parsed.url:
				base = parsed.url.split("/eng@", 1)[0]
				candidates = [
					f"{base}/eng@/main.xml",
					f"{base}/eng@/main",
					f"{base}/eng@.xml",
					f"{base}/eng@/document.xml",
				]
				akn_text: str | None = None
				for xml_url in candidates:
					try:
						xml_resp = http_client.download(xml_url)
						if not xml_resp.content:
							continue
						if (xml_resp.content_type or "").lower().find("xml") == -1 and not xml_url.endswith(".xml"):
							continue
						path = save_xml(xml_url, xml_resp.content)
						text_candidate = extract_plain_text_from_akn(xml_resp.content)
						if text_candidate and len(text_candidate) > (len(akn_text or "")):
							akn_text = text_candidate
					except Exception:
						continue
				if akn_text and (not parsed.content_text or len(parsed.content_text or "") < len(akn_text)):
					parsed.content_text = akn_text
					# Also persist immediately to the case
					case.content_text = akn_text
					from .db import db_write_lock
					with db_write_lock:
						session.flush()
						session.commit()
		except Exception:
			pass

		first_pdf_text: str | None = None
		# Download PDFs
		for link in parsed.pdf_links:
			abs_url = normalize_url(parsed.url, link)
			try:
				pdf_resp = http_client.download(abs_url)
				path = save_pdf(abs_url, pdf_resp.content, pdf_resp.content_type)
				doc = Document(case_id=case.id, file_path=str(path), url=abs_url, content_type=pdf_resp.content_type)
				session.add(doc)
				from .db import db_write_lock
				with db_write_lock:
					session.flush()
					session.commit()
				if first_pdf_text is None and deep:
					try:
						reader = PdfReader(str(path))
						text_parts = []
						for page in reader.pages[:20]:
							text_parts.append(page.extract_text() or "")
						first_pdf_text = "\n".join(text_parts).strip() or None
					except Exception:
						pass
			except Exception:
				continue

		# Download images
		for link in parsed.image_links:
			abs_url = normalize_url(parsed.url, link)
			try:
				img_resp = http_client.download(abs_url)
				path = save_image(abs_url, img_resp.content, img_resp.content_type)
				img = Image(case_id=case.id, file_path=str(path), url=abs_url)
				session.add(img)
				from .db import db_write_lock
				with db_write_lock:
					session.flush()
					session.commit()
			except Exception:
				continue

		# Fill content_text if still small and we have PDF text
		if deep and (not case.content_text or len(case.content_text) < 800) and first_pdf_text:
			case.content_text = first_pdf_text
			from .db import db_write_lock
			with db_write_lock:
				session.flush()
				session.commit()

		return case.id


def crawl_listing(start_url: str, max_pages: int | None = None, deep: bool = False) -> list[int]:
	ids: list[int] = []
	page_count = 0
	current_url = start_url
	while current_url:
		resp = http_client.get(current_url)
		save_html_snapshot(resp.url, resp.text)
		links, next_link = extract_listing_links(resp.url, resp.text)
		for href in links:
			case_url = normalize_url(resp.url, href)
			try:
				case_id = scrape_case_detail(case_url, deep=deep)
				ids.append(case_id)
			except Exception:
				continue

		page_count += 1
		if max_pages and page_count >= max_pages:
			break
		current_url = normalize_url(resp.url, next_link) if next_link else None

	return ids


def scrape_url(url: str, deep: bool = False) -> list[int]:
	resp = http_client.get(url)
	save_html_snapshot(resp.url, resp.text)
	if is_listing_page(resp.text):
		return crawl_listing(resp.url, deep=deep)
	else:
		return [scrape_case_detail(resp.url, deep=deep)]


def search_and_scrape(query: str, start_url: str = "https://new.kenyalaw.org/judgments/", deep: bool = False) -> list[int]:
	"""
	Naive query helper: fetch the listing page with q parameter patterns if present.
	If the site supports search querystring, attempt it; otherwise fallback to scanning first pages.
	"""
	# Try basic querystring param variants commonly used
	candidates = [
		f"{start_url}?q={query}",
		f"{start_url}?search={query}",
		f"{start_url}?query={query}",
	]
	all_ids: list[int] = []
	for url in candidates:
		try:
			ids = crawl_listing(url, max_pages=3, deep=deep)
			if ids:
				all_ids.extend(ids)
		except Exception:
			continue
	return list(dict.fromkeys(all_ids))


