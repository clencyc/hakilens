from __future__ import annotations

import argparse
import sys

from .db import init_db
from .scraper import scrape_url, crawl_listing, scrape_case_detail


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Hakilens Kenya Law scraper")
	sub = parser.add_subparsers(dest="cmd", required=True)

	# scrape-url
	sp = sub.add_parser("scrape-url", help="Scrape a single URL (case detail or listing)")
	sp.add_argument("url", help="URL to scrape")

	# crawl-listing
	cp = sub.add_parser("crawl-listing", help="Crawl a listing with pagination")
	cp.add_argument("url", help="Listing URL to start from")
	cp.add_argument("--max-pages", type=int, default=None, help="Optional max pages to crawl")

	# case-detail
	dp = sub.add_parser("case-detail", help="Scrape a known case detail URL only")
	dp.add_argument("url", help="Case detail URL")

	# scheduled-run (example target)
	sub.add_parser("scheduled-run", help="Default scheduled crawl entrypoint")

	args = parser.parse_args(argv)
	init_db()

	if args.cmd == "scrape-url":
		ids = scrape_url(args.url)
		print("Saved case IDs:", ids)
		return 0
	elif args.cmd == "crawl-listing":
		ids = crawl_listing(args.url, max_pages=args.max_pages)
		print("Saved case IDs:", ids)
		return 0
	elif args.cmd == "case-detail":
		cid = scrape_case_detail(args.url)
		print("Saved case ID:", cid)
		return 0
	elif args.cmd == "scheduled-run":
		# Example: crawl the legislation landing page
		ids = crawl_listing("https://new.kenyalaw.org/judgments/", max_pages=5)
		print("Saved case IDs:", ids)
		return 0

	return 1


if __name__ == "__main__":
	sys.exit(main())


