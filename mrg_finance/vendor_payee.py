"""Vendor payee defaults and conservative discovery from official structured contact data."""

import html
import json
import re
from urllib.parse import urljoin, urlparse

import requests


KNOWN_PAYEES = {
    "amazon": {
        "name": "Amazon.com Services LLC",
        "address": "410 Terry Avenue North, Seattle, WA 98109, USA",
        "source": "https://shipping.amazon.com/privacy-notice",
    },
    "digikey": {
        "name": "Digi-Key Electronics",
        "address": "701 Brooks Avenue South, Thief River Falls, MN 56701, USA",
        "phone": "1-800-344-4539",
        "email": "orders@digikey.com",
        "source": "https://www.digikey.com/en/help/browser-support",
    },
}


def vendor_key(name):
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    if normalized in ("amazon", "amazoncom", "amazonbusiness"):
        return "amazon"
    if normalized in ("digikey", "digikeyelectronics"):
        return "digikey"
    return normalized


def _organizations(data):
    if isinstance(data, list):
        for child in data:
            yield from _organizations(child)
    elif isinstance(data, dict):
        kind = data.get("@type", [])
        types = [kind] if isinstance(kind, str) else kind
        if any(t in ("Organization", "Corporation", "Store", "LocalBusiness") for t in types):
            yield data
        for child in data.values():
            if isinstance(child, (list, dict)):
                yield from _organizations(child)


def lookup_vendor_payee(vendor, product_url):
    key = vendor_key(vendor)
    if key in KNOWN_PAYEES:
        return dict(KNOWN_PAYEES[key])
    parsed = urlparse(product_url)
    result = {"name": vendor, "source": None}
    if parsed.scheme != "https" or not parsed.hostname:
        return result
    origin = f"https://{parsed.netloc}"
    urls = [origin, urljoin(origin, "/contact"), urljoin(origin, "/contact-us")]
    for url in urls:
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            if urlparse(response.url).hostname != parsed.hostname:
                continue
            scripts = re.findall(r'<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', response.text, re.S | re.I)
            for script in scripts:
                for org in _organizations(json.loads(html.unescape(script))):
                    # Ignore parent-company/contact data belonging to another website.
                    org_url = org.get("url")
                    if org_url and urlparse(org_url).hostname not in (None, parsed.hostname):
                        continue
                    address = org.get("address")
                    if not isinstance(address, dict) or not address.get("streetAddress"):
                        continue
                    country = address.get("addressCountry")
                    if isinstance(country, dict):
                        country = country.get("name")
                    result.update({
                        "name": org.get("legalName") or org.get("name") or vendor,
                        "address": ", ".join(str(v) for v in (
                            address.get("streetAddress"), address.get("addressLocality"),
                            address.get("addressRegion"), address.get("postalCode"), country,
                        ) if v),
                        "phone": org.get("telephone"), "email": org.get("email"), "source": response.url,
                    })
                    return result
        except (requests.RequestException, ValueError, TypeError):
            continue
    return result
