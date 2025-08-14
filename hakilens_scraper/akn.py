from __future__ import annotations

from lxml import etree


def extract_plain_text_from_akn(xml_bytes: bytes) -> str:
	parser = etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True)
	root = etree.fromstring(xml_bytes, parser=parser)
	nsmap = {k if k else "akn": v for k, v in (root.nsmap or {}).items()}
	# Try common body containers in Akoma Ntoso
	body_candidates = [
		"//akn:body",
		"//body",
		"//akn:judgment/akn:body",
		"//akn:act/akn:body",
	]
	text_parts: list[str] = []
	for xpath in body_candidates:
		nodes = root.xpath(xpath, namespaces=nsmap)
		if not nodes:
			continue
		for node in nodes:
			for p in node.xpath(".//text()", namespaces=nsmap):
				val = (p or "").strip()
				if val:
					text_parts.append(val)
		if text_parts:
			break
	return "\n".join(text_parts)


