from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from .config import settings


def _sha1(text: str) -> str:
	return hashlib.sha1(text.encode("utf-8")).hexdigest()


def save_html_snapshot(url: str, html: str) -> Path:
	filename = f"{_sha1(url)}.html"
	path = settings.html_dir / filename
	path.write_text(html, encoding="utf-8")
	return path


def _ext_from_content_type(content_type: Optional[str], default: str) -> str:
	if not content_type:
		return default
	if "pdf" in content_type:
		return ".pdf"
	if "jpeg" in content_type or "jpg" in content_type:
		return ".jpg"
	if "png" in content_type:
		return ".png"
	if "gif" in content_type:
		return ".gif"
	return default


def save_pdf(url: str, content: bytes, content_type: Optional[str]) -> Path:
	filename = f"{_sha1(url)}{_ext_from_content_type(content_type, '.pdf')}"
	path = settings.pdf_dir / filename
	path.write_bytes(content)
	return path


def save_image(url: str, content: bytes, content_type: Optional[str]) -> Path:
	filename = f"{_sha1(url)}{_ext_from_content_type(content_type, '.img')}"
	path = settings.image_dir / filename
	path.write_bytes(content)
	return path


def save_xml(url: str, content: bytes) -> Path:
	filename = f"{_sha1(url)}.xml"
	path = settings.xml_dir / filename
	path.write_bytes(content)
	return path


