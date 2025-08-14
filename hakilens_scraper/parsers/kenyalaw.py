from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from bs4 import BeautifulSoup


@dataclass
class CaseParsed:
	url: str
	title: Optional[str]
	case_number: Optional[str]
	court: Optional[str]
	parties: Optional[str]
	judges: Optional[str]
	date: Optional[str]
	citation: Optional[str]
	content_text: Optional[str]
	pdf_links: list[str]
	image_links: list[str]


def is_listing_page(html: str) -> bool:
	soup = BeautifulSoup(html, "lxml")
	# Heuristic: listing pages have multiple result cards/rows and pagination
	if soup.select("a[rel='next']"):
		return True
	# Common listing item containers
	if len(soup.select(".result, .results, .list, .search-results, .card")) >= 5:
		return True
	return False


def extract_listing_links(base_url: str, html: str) -> tuple[list[str], Optional[str]]:
	"""Return (detail_links, next_page_url). Both are absolute or relative as found."""
	soup = BeautifulSoup(html, "lxml")
	# Detail links: try anchors that look like case detail
	detail_links: set[str] = set()
	for a in soup.find_all("a"):
		href = a.get("href")
		if not href:
			continue
		text = (a.get_text() or "").lower()
		if any(k in text for k in ["read more", "view", "case", "judgment", "ruling"]):
			detail_links.add(href)
		elif any(k in (href.lower()) for k in ["/case", "/judgment", "/ruling", "/download"]):
			detail_links.add(href)

	# Next pagination link
	next_link = None
	for sel in ["a[rel='next']", "a.page-next", "li.next a", "nav.pagination a"]:
		candidate = soup.select_one(sel)
		if candidate and candidate.get("href"):
			next_link = candidate["href"]
			break
	# Fallback: find an anchor with text 'Next'
	if not next_link:
		for a in soup.find_all("a"):
			if (a.get_text() or "").strip().lower() == "next" and a.get("href"):
				next_link = a["href"]
				break

	return list(detail_links), next_link


def _join_text(elements: Iterable) -> str:
	parts: list[str] = []
	for el in elements:
		text = el.get_text(" ", strip=True)
		if text:
			parts.append(text)
	return "\n".join(parts)


def parse_case_detail(url: str, html: str) -> CaseParsed:
	soup = BeautifulSoup(html, "lxml")

	# Naive extraction with fallbacks; adjust selectors as we learn the DOM
	title = None
	for sel in ["h1", "h2", ".title", ".case-title"]:
		el = soup.select_one(sel)
		if el:
			title = el.get_text(strip=True)
			break

	meta_map = {
		"case_number": [".case-number", "#case-number"],
		"court": [".court"],
		"parties": [".parties"],
		"judges": [".judges"],
		"date": [".date"],
		"citation": [".citation"],
	}

	def first_text(selectors: list[str]) -> Optional[str]:
		for sel in selectors:
			el = soup.select_one(sel)
			if el:
				return el.get_text(" ", strip=True)
		return None

	# Generic label-value scraping across common patterns
	def scan_label_value() -> dict[str, str]:
		labels = {
			"case_number": ["case number", "case no", "case no."],
			"court": ["court"],
			"parties": ["parties", "between"],
			"judges": ["judge", "judges", "coram"],
			"date": ["date", "delivered", "decision date"],
			"citation": ["citation"],
			"counsel": ["counsel", "advocates"],
		}
		found: dict[str, str] = {}
		# dl/dt/dd
		for dl in soup.find_all("dl"):
			for dt in dl.find_all("dt"):
				label = (dt.get_text(" ", strip=True) or "").lower()
				dd = dt.find_next("dd")
				value = dd.get_text(" ", strip=True) if dd else None
				if not value:
					continue
				for key, kws in labels.items():
					if any(k in label for k in kws) and key not in found:
						found[key] = value
		# tables th/td
		for table in soup.find_all("table"):
			for th in table.find_all("th"):
				label = (th.get_text(" ", strip=True) or "").lower()
				td = th.find_next("td")
				value = td.get_text(" ", strip=True) if td else None
				if not value:
					continue
				for key, kws in labels.items():
					if any(k in label for k in kws) and key not in found:
						found[key] = value
		# paragraphs like "Judge: ..." or "Parties: ..."
		for p in soup.find_all(["p", "li"]):
			text = (p.get_text(" ", strip=True) or "")
			low = text.lower()
			for key, kws in labels.items():
				for k in kws:
					if low.startswith(k + ":") and key not in found:
						found[key] = text.split(":", 1)[1].strip()
		return found

	# Fallbacks for common label/value layouts
	def find_label_value(label_keywords: list[str]) -> Optional[str]:
		for dl in soup.find_all(["dl", "table"]):
			text = dl.get_text(" ", strip=True).lower()
			if not any(k in text for k in label_keywords):
				continue
			# Try definition lists
			for dt in dl.find_all("dt"):
				label = (dt.get_text(" ", strip=True) or "").lower()
				if any(k in label for k in label_keywords):
					dd = dt.find_next("dd")
					if dd:
						return dd.get_text(" ", strip=True)
			# Try tables
			for th in dl.find_all("th"):
				label = (th.get_text(" ", strip=True) or "").lower()
				if any(k in label for k in label_keywords):
					td = th.find_next("td")
					if td:
						return td.get_text(" ", strip=True)
		return None

	labels_found = scan_label_value()
	case_number = first_text(meta_map["case_number"]) or labels_found.get("case_number") or find_label_value(["case number", "case no"]) 
	court = first_text(meta_map["court"]) or labels_found.get("court") or find_label_value(["court"]) 
	parties = first_text(meta_map["parties"]) or labels_found.get("parties") or find_label_value(["parties", "appellant", "respondent"]) 
	judges = first_text(meta_map["judges"]) or labels_found.get("judges") or find_label_value(["judge", "judges", "coram"]) 
	date = first_text(meta_map["date"]) or labels_found.get("date") or find_label_value(["date", "delivered", "decision date"]) 
	citation = first_text(meta_map["citation"]) or labels_found.get("citation") or find_label_value(["citation"]) 

	# Content paragraphs (expanded heuristics)
	content_container = None
	for sel in [
		"main",
		"article",
		".content",
		"#content",
		".judgment-text",
		".case-body",
		"[class*='akn']",
		".document",
		".entry-content",
	]:
		cand = soup.select_one(sel)
		if cand:
			content_container = cand
			break

	content_text = None
	if content_container:
		# remove common non-content blocks (breadcrumbs, nav, sidebars)
		for rem_sel in [
			".breadcrumbs", ".breadcrumb", "nav", ".nav", ".menu", ".header", "header", ".footer", "footer", "aside", ".sidebar",
		]:
			for el in content_container.select(rem_sel):
				el.decompose()
		# Prefer rich join across common textual elements
		text_nodes = content_container.find_all(["p", "li", "pre", "blockquote", "h2", "h3", "h4"]) or []
		if text_nodes:
			content_text = _join_text(text_nodes)
		else:
			# Fallback: get text of container directly
			content_text = content_container.get_text("\n", strip=True)

	# Resources
	pdf_links: list[str] = []
	image_links: list[str] = []
	for a in soup.find_all("a"):
		href = a.get("href")
		if not href:
			continue
		text = (a.get_text(" ", strip=True) or "").lower()
		if any(href.lower().endswith(ext) for ext in [".pdf"]) or ("pdf" in text and "download" in text):
			pdf_links.append(href)
		elif any(href.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]):
			image_links.append(href)

	return CaseParsed(
		url=url,
		title=title,
		case_number=case_number,
		court=court,
		parties=parties,
		judges=judges,
		date=date,
		citation=citation,
		content_text=content_text,
		pdf_links=list(dict.fromkeys(pdf_links)),
		image_links=list(dict.fromkeys(image_links)),
	)


