from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.made-in-china.com"
MISSING_TEXT = {"", "n/a", "na", "none", "null", "unknown"}


PRODUCT_MATCH_FIELDS = (
    "product_id",
    "name",
    "product_url",
    "product_image_url",
    "price",
    "price_min",
    "price_max",
    "currency",
    "min_order",
    "moq_quantity",
    "moq_unit",
    "product_attributes",
    "secured_trading",
    "is_sponsored",
    "match_rank",
    "result_page",
)


SUPPLIER_FIELDS = (
    "company_id",
    "vendor_name",
    "vendor_profile_url",
    "supplier_from",
    "business_type",
    "member_type",
    "member_since",
    "year_established",
    "employee_count",
    "address",
    "average_response_time",
    "supplier_rating",
    "supplier_capability_index",
    "company_description",
)


SUPPLIER_BOOLEAN_FIELDS = (
    "audited_supplier",
    "leading_factory",
)


SUPPLIER_LIST_FIELDS = (
    "main_products",
    "supplier_capability_tags",
)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_image_reference(value: str) -> str:
    """Return a plain image URL when an input was pasted as a Markdown link."""
    text = (value or "").strip()
    markdown_link = re.fullmatch(
        r"!?\[[^\]]*]\(\s*<?(https?://[^>\s]+)>?\s*\)",
        text,
        re.IGNORECASE,
    )
    return markdown_link.group(1) if markdown_link else text


def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in MISSING_TEXT
    if isinstance(value, (list, tuple, dict, set)):
        return not value
    return False


def normalize_mic_url(value: str, *, strip_query: bool = False) -> str:
    value = clean_text(value)
    if not value or value.lower().startswith("javascript:"):
        return ""

    absolute = urljoin(f"{BASE_URL}/", value)

    try:
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        scheme = "https" if host == "made-in-china.com" or host.endswith(".made-in-china.com") else parsed.scheme
        query = "" if strip_query else parsed.query
        return parsed._replace(scheme=scheme, query=query, fragment="").geturl()
    except Exception:
        return absolute


def canonicalize_mic_url(value: str) -> str:
    return normalize_mic_url(value, strip_query=True)


def extract_product_id(product_url: str = "", candidate: str = "") -> str | None:
    candidate = clean_text(candidate)
    if re.fullmatch(r"[A-Za-z0-9]{8,24}", candidate):
        return candidate

    for pattern in (
        r"/product/([A-Za-z0-9]{8,24})(?:/|$)",
        r"prodetail_[^/?#]*_([A-Za-z0-9]{8,24})\.html",
        r"(?:pdid|productId)=([A-Za-z0-9]{8,24})",
    ):
        match = re.search(pattern, product_url or "", re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def parse_tracking(value: str) -> dict:
    values: dict[str, str] = {}
    for part in (value or "").split(","):
        if ":" not in part:
            continue
        key, raw = part.split(":", 1)
        values[key.strip()] = raw.strip()

    product_id = values.get("pdid") or None
    company_id = values.get("pcid") or None
    ad_service = values.get("ads_srv_tp", "").lower()
    is_sponsored = bool(values.get("aid")) or ad_service.startswith("ad") or "sponsor" in ad_service

    return {
        "product_id": product_id,
        "company_id": company_id,
        "is_sponsored": is_sponsored,
    }


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def parse_price_details(value: str) -> dict:
    text = clean_text(value)
    if is_missing(text):
        return {"price_min": None, "price_max": None, "currency": None}

    upper = text.upper()
    currency = None
    if "CAD" in upper or "CA$" in upper or "C$" in upper:
        currency = "CAD"
    elif "USD" in upper or "US$" in upper or "$" in text:
        currency = "USD"
    elif "EUR" in upper or "€" in text:
        currency = "EUR"
    elif "GBP" in upper or "£" in text:
        currency = "GBP"
    elif "CNY" in upper or "RMB" in upper or "CN¥" in upper or "￥" in text:
        currency = "CNY"

    numbers: list[float] = []
    for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            numbers.append(_number(raw))
        except ValueError:
            continue

    if not numbers:
        return {"price_min": None, "price_max": None, "currency": currency}

    return {
        "price_min": numbers[0],
        "price_max": numbers[1] if len(numbers) > 1 else numbers[0],
        "currency": currency,
    }


def parse_moq_details(value: str) -> dict:
    text = re.sub(r"\(\s*MOQ\s*\)", "", value or "", flags=re.IGNORECASE)
    text = re.sub(
        r"^\s*(?:min\.?\s*order|minimum\s+order(?:\s+quantity)?)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = clean_text(text)

    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(.*)", text)
    if not match:
        return {"moq_quantity": None, "moq_unit": None}

    try:
        quantity = _number(match.group(1))
    except ValueError:
        quantity = None

    if quantity is not None and quantity.is_integer():
        quantity = int(quantity)

    unit = clean_text(match.group(2)).strip(" .:-") or None
    return {"moq_quantity": quantity, "moq_unit": unit}


def parse_rating(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*5", value or "")
    return float(match.group(1)) if match else None


def parse_integer(value: str) -> int | None:
    match = re.search(r"\d[\d,]*", value or "")
    return int(match.group(0).replace(",", "")) if match else None


def _text(node: Tag | None) -> str:
    return clean_text(node.get_text(" ", strip=True)) if node else ""


def _select_text(node: Tag, selectors: Iterable[str]) -> str:
    for selector in selectors:
        found = node.select_one(selector)
        value = _text(found)
        if value:
            return value
    return ""


def _select_attr(node: Tag, selectors: Iterable[str], attributes: Iterable[str]) -> str:
    for selector in selectors:
        for found in node.select(selector):
            for attribute in attributes:
                value = clean_text(str(found.get(attribute) or ""))
                if value and "space.png" not in value:
                    return value
    return ""


def _own_text(node: Tag) -> str:
    return clean_text(" ".join(str(item) for item in node.find_all(string=True, recursive=False)))


def _image_url(node: Tag) -> str:
    selectors = (
        ".prod-img img[data-original]",
        ".prod-img img[src]",
        ".img-thumb-inner img[data-original]",
        ".img-thumb-inner img[src]",
    )
    return normalize_mic_url(_select_attr(node, selectors, ("data-original", "src")))


def _attributes(node: Tag) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in node.select(".property-list li"):
        text = _text(item)
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        key = clean_text(key)
        value = clean_text(value)
        if key and value:
            values[key] = value
    return values


def _supplier_tags(node: Tag) -> list[str]:
    tags: list[str] = []
    for item in node.select(".verified-list .verified-item"):
        value = _own_text(item)
        if value and value not in tags:
            tags.append(value)
    return tags


def _member_type(node: Tag) -> str | None:
    for image in node.select("img[alt]"):
        alt = clean_text(str(image.get("alt") or ""))
        if alt in {"Gold Member", "Diamond Member"}:
            return alt
    return None


def _finalize_record(record: dict) -> dict:
    record["product_url"] = canonicalize_mic_url(str(record.get("product_url") or ""))
    record["vendor_profile_url"] = canonicalize_mic_url(str(record.get("vendor_profile_url") or ""))
    record["product_image_url"] = normalize_mic_url(str(record.get("product_image_url") or "")) or None
    record["product_id"] = extract_product_id(
        str(record.get("product_url") or ""),
        str(record.get("product_id") or ""),
    )
    record.update(parse_price_details(str(record.get("price") or "")))
    record.update(parse_moq_details(str(record.get("min_order") or "")))
    return record


def parse_text_search_html(html: str, *, result_page: int = 1, rank_offset: int = 0) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    cards = soup.select(".search-list .list-node") or soup.select(".list-node")
    records: list[dict] = []

    for card in cards:
        product_link = card.select_one("h2.product-name a[href], a.product-detail[href]")
        supplier_link = card.select_one(".company-info a.J-compnay-name[href], .company-info a.compnay-name[href]")
        if not product_link or not supplier_link:
            continue

        tracking = parse_tracking(str(product_link.get("ads-data") or supplier_link.get("ads-data") or ""))
        price = _select_text(card, (".product-property strong.price", ".price-info strong.price")) or "N/A"
        minimum_order = ""
        for item in card.select(".product-property .info"):
            value = _text(item)
            if "MOQ" in value.upper():
                minimum_order = clean_text(re.sub(r"\(\s*MOQ\s*\)", "", value, flags=re.IGNORECASE))
                break

        supplier_location = _select_text(
            card,
            (".company-address-info .tip-para", ".company-address-info [class*='tip'] p"),
        ) or "N/A"
        business_type = _select_text(card, (".company-tag .tag-list",)) or "N/A"
        rating_text = _select_text(card, (".company-name-popup a.rate", ".company-name-popup .rate"))

        record = {
            "name": _text(product_link) or clean_text(str(product_link.get("title") or "")) or "N/A",
            "product_id": tracking.get("product_id"),
            "product_url": str(product_link.get("href") or ""),
            "product_image_url": _image_url(card),
            "price": price,
            "min_order": minimum_order or "N/A",
            "product_attributes": _attributes(card),
            "secured_trading": bool(
                card.select_one("[data-icon-alt*='Secured Trading'], .trade-btn-holder, .secured-trading-icon")
            ),
            "is_sponsored": bool(tracking.get("is_sponsored")),
            "match_rank": rank_offset + len(records) + 1,
            "result_page": result_page,
            "vendor_name": _text(supplier_link) or clean_text(str(supplier_link.get("title") or "")) or "N/A",
            "vendor_profile_url": str(supplier_link.get("href") or ""),
            "company_id": tracking.get("company_id"),
            "audited_supplier": bool(card.select_one("img[alt='Audited Supplier']")),
            "leading_factory": bool(card.select_one("img[alt*='Industry-leading Audited Factory']")),
            "member_type": _member_type(card),
            "supplier_rating": parse_rating(rating_text),
            "supplier_capability_index": len(card.select(".auth-icon-item.icon-star img")) or None,
            "supplier_from": supplier_location,
            "business_type": business_type,
            "supplier_capability_tags": _supplier_tags(card),
            "main_products": [],
            "member_since": None,
            "year_established": None,
            "employee_count": None,
            "address": None,
            "average_response_time": None,
            "company_description": None,
        }
        records.append(_finalize_record(record))

    return records


def parse_image_search_html(html: str, *, result_page: int = 1, rank_offset: int = 0) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    cards = soup.select(".products-item")
    records: list[dict] = []

    for card in cards:
        product_link = card.select_one(".product-name a[href]")
        supplier_link = card.select_one(".company-name a.compnay-name[href], .company-name a[href]")
        if not product_link or not supplier_link:
            continue

        tracking = parse_tracking(str(product_link.get("ads-data") or supplier_link.get("ads-data") or ""))
        price = _select_text(card, (".product-property strong.price",)) or "N/A"
        minimum_order = ""
        for item in card.select(".product-property .attr-item"):
            value = _text(item)
            if "MOQ" in value.upper():
                minimum_order = clean_text(re.sub(r"\(\s*MOQ\s*\)", "", value, flags=re.IGNORECASE))
                break

        record = {
            "name": _text(product_link) or clean_text(str(product_link.get("title") or "")) or "N/A",
            "product_id": tracking.get("product_id"),
            "product_url": str(product_link.get("href") or ""),
            "product_image_url": _image_url(card),
            "price": price,
            "min_order": minimum_order or "N/A",
            "product_attributes": {},
            "secured_trading": bool(card.select_one(".secured-trading-icon, img[alt*='Secured Trading']")),
            "is_sponsored": bool(tracking.get("is_sponsored")),
            "match_rank": rank_offset + len(records) + 1,
            "result_page": result_page,
            "vendor_name": _text(supplier_link) or clean_text(str(supplier_link.get("title") or "")) or "N/A",
            "vendor_profile_url": str(supplier_link.get("href") or ""),
            "company_id": tracking.get("company_id"),
            "audited_supplier": bool(card.select_one("img[alt='Audited Supplier']")),
            "leading_factory": bool(card.select_one("img[alt*='Industry-leading Audited Factory']")),
            "member_type": _member_type(card),
            "supplier_rating": None,
            "supplier_capability_index": None,
            "supplier_from": "N/A",
            "business_type": "N/A",
            "supplier_capability_tags": [],
            "main_products": [],
            "member_since": None,
            "year_established": None,
            "employee_count": None,
            "address": None,
            "average_response_time": None,
            "company_description": None,
        }
        records.append(_finalize_record(record))

    return records


def parse_total_count(html: str) -> int | None:
    soup = BeautifulSoup(html or "", "html.parser")
    field = soup.select_one("input[name='totalCount']")
    return parse_integer(str(field.get("value") or "")) if field else None


def parse_supplier_profile_html(html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    details: dict = {}

    name = _select_text(soup, (".sr-comInfo-title h1", "h1"))
    if name:
        details["vendor_name"] = name

    location = _select_text(soup, (".sr-comInfo-details .detail-address", ".detail-address"))
    if location:
        details["supplier_from"] = location

    for item in soup.select(".sr-comInfo-details .info-item"):
        label = _select_text(item, (".info-label", ".info-label-txt"))
        field = item.select_one(".info-fields")
        value = _text(field)
        normalized = label.rstrip(":").lower()
        if not value:
            continue
        if normalized == "business type":
            details["business_type"] = value
        elif normalized == "main products":
            products = [_text(link) for link in field.select("a") if _text(link)] if field else []
            details["main_products"] = list(dict.fromkeys(products or [value]))
        elif normalized in {"year of establishment", "year established"}:
            details["year_established"] = value
        elif normalized == "number of employees":
            details["employee_count"] = parse_integer(value)
        elif normalized == "address":
            details["address"] = value

    member_type = _select_text(soup, ("#member-since .sign-item-text",))
    if member_type:
        details["member_type"] = member_type

    member_since = _select_text(soup, ("#member-since .txt-year",))
    year_match = re.search(r"\b(19|20)\d{2}\b", member_since)
    if year_match:
        details["member_since"] = int(year_match.group(0))

    rating = parse_rating(_select_text(soup, (".review-scores .score-item-rating", ".score-item-rating")))
    if rating is not None:
        details["supplier_rating"] = rating

    response_time = _select_text(soup, (".average-response-time .response-time-data",))
    if response_time:
        details["average_response_time"] = response_time

    description = _select_text(soup, (".detail-intro",))
    if description:
        details["company_description"] = description

    details["audited_supplier"] = bool(soup.select_one("img[alt='Audited Supplier']"))
    details["leading_factory"] = bool(soup.select_one("img[alt*='Industry-leading Audited Factory']"))

    capability_index = len(soup.select(".sr-comInfo-sign .icon-star img"))
    if capability_index:
        details["supplier_capability_index"] = capability_index

    company_match = re.search(r"sendInquiry/shrom_([A-Za-z0-9]+)_", html or "")
    if company_match:
        details["company_id"] = company_match.group(1)

    return details


def apply_supplier_details(record: dict, details: dict) -> None:
    for field in SUPPLIER_BOOLEAN_FIELDS:
        if details.get(field):
            record[field] = True

    for field in SUPPLIER_LIST_FIELDS:
        incoming = details.get(field)
        if not incoming:
            continue
        current = record.setdefault(field, [])
        for value in incoming:
            if value not in current:
                current.append(value)

    for field in SUPPLIER_FIELDS:
        if not is_missing(details.get(field)):
            record[field] = details[field]


def build_product_match(record: dict, search_input: str, search_type: str) -> dict:
    match = {field: record.get(field) for field in PRODUCT_MATCH_FIELDS}
    match["search_input"] = search_input
    match["search_type"] = search_type
    return match


def initialize_supplier_record(record: dict, search_input: str, search_type: str) -> dict:
    result = dict(record)
    result["search_input"] = search_input
    result["search_type"] = search_type
    result["matched_search_inputs"] = [search_input]
    result["matched_products"] = [build_product_match(record, search_input, search_type)]
    return result


def merge_supplier_record(existing: dict, incoming: dict, search_input: str, search_type: str) -> bool:
    matched_inputs = existing.setdefault("matched_search_inputs", [])
    if search_input not in matched_inputs:
        matched_inputs.append(search_input)

    for field in SUPPLIER_BOOLEAN_FIELDS:
        if incoming.get(field):
            existing[field] = True

    for field in SUPPLIER_LIST_FIELDS:
        current_values = existing.setdefault(field, [])
        for value in incoming.get(field) or []:
            if value not in current_values:
                current_values.append(value)

    for field in SUPPLIER_FIELDS:
        if is_missing(existing.get(field)) and not is_missing(incoming.get(field)):
            existing[field] = incoming.get(field)

    product_match = build_product_match(incoming, search_input, search_type)
    identity = (
        product_match.get("product_id") or product_match.get("product_url") or product_match.get("name"),
        search_type,
        search_input,
    )

    matched_products = existing.setdefault("matched_products", [])
    for current in matched_products:
        current_identity = (
            current.get("product_id") or current.get("product_url") or current.get("name"),
            current.get("search_type"),
            current.get("search_input"),
        )
        if current_identity == identity:
            return False

    matched_products.append(product_match)
    return True


def upsert_supplier_record(
    suppliers_by_key: dict[str, dict],
    seen_supplier_keys: set[str],
    key: str,
    record: dict,
    search_input: str,
    search_type: str,
    max_unique_for_input: int,
    max_unique_total: int | None = None,
) -> tuple[dict | None, bool]:
    """Add or merge a card while enforcing a separate supplier cap per input."""
    existing = suppliers_by_key.get(key)

    if key in seen_supplier_keys:
        if existing is not None:
            merge_supplier_record(existing, record, search_input, search_type)
        return existing, False

    if len(seen_supplier_keys) >= max_unique_for_input:
        return None, False

    if existing is None and max_unique_total is not None and len(suppliers_by_key) >= max_unique_total:
        return None, False

    seen_supplier_keys.add(key)

    if existing is not None:
        merge_supplier_record(existing, record, search_input, search_type)
        return existing, False

    supplier_record = initialize_supplier_record(record, search_input, search_type)
    suppliers_by_key[key] = supplier_record
    return supplier_record, True


def normalize_company_name(name: str) -> str:
    value = (name or "").lower()
    value = re.sub(r"[,.–—\-\s]+", " ", value)
    value = re.sub(r"\b(?:co|company|inc|ltd|limited)\b", "", value)
    return re.sub(r"\s+", " ", value).strip()


def key_for_dedupe(vendor_name: str, profile_url: str, product_url: str = "") -> str:
    canonical_profile = canonicalize_mic_url(profile_url)
    if canonical_profile:
        parsed = urlparse(canonical_profile)
        if parsed.hostname:
            return f"url:{parsed.hostname.lower()}"

    normalized_name = normalize_company_name(vendor_name)
    if normalized_name and normalized_name not in MISSING_TEXT:
        return f"name:{normalized_name}"

    canonical_product = canonicalize_mic_url(product_url)
    return f"product:{canonical_product}" if canonical_product else ""
