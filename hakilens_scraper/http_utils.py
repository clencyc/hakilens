from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential_jitter


@dataclass
class HttpResponse:
	url: str
	status_code: int
	text: str
	content: bytes
	content_type: Optional[str]


class HttpClient:
	def __init__(self) -> None:
		# Import settings here to avoid circular imports
		from .config import settings
		
		self.session = requests.Session()
		self.session.headers.update({
			"User-Agent": settings.user_agent,
			"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		})
		self.rate_limit_window = 60.0
		self.max_requests_per_window = max(1, settings.requests_per_minute)
		self.min_interval = self.rate_limit_window / self.max_requests_per_window
		self._last_request_time = 0.0
		self.request_timeout_seconds = settings.request_timeout_seconds
		
		self.proxies = {}
		if settings.http_proxy:
			self.proxies["http"] = settings.http_proxy
		if settings.https_proxy:
			self.proxies["https"] = settings.https_proxy

	def _respect_rate_limit(self) -> None:
		now = time.time()
		delta = now - self._last_request_time
		if delta < self.min_interval:
			time.sleep(self.min_interval - delta)
		self._last_request_time = time.time()

	@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
	def get(self, url: str) -> HttpResponse:
		self._respect_rate_limit()
		resp = self.session.get(url, timeout=self.request_timeout_seconds, proxies=self.proxies)
		resp.raise_for_status()
		return HttpResponse(
			url=resp.url,
			status_code=resp.status_code,
			text=resp.text,
			content=resp.content,
			content_type=resp.headers.get("Content-Type"),
		)

	@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
	def download(self, url: str) -> HttpResponse:
		self._respect_rate_limit()
		resp = self.session.get(url, timeout=self.request_timeout_seconds, proxies=self.proxies, stream=True)
		resp.raise_for_status()
		content = resp.content
		return HttpResponse(
			url=resp.url,
			status_code=resp.status_code,
			text="",
			content=content,
			content_type=resp.headers.get("Content-Type"),
		)


http_client = HttpClient()


