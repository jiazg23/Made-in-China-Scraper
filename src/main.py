from __future__ import annotations

import atexit
import asyncio
import csv
import io
import ipaddress
import json
import logging
import mimetypes
import os
import re
import shutil
import socket
import struct
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from apify import Actor
from PIL import Image, ImageOps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from parsing import (
    PRODUCT_MATCH_FIELDS,
    apply_supplier_details,
    key_for_dedupe,
    normalize_image_reference,
    normalize_mic_url,
    parse_image_search_html,
    parse_supplier_profile_html,
    parse_text_search_html,
    parse_total_count,
    upsert_supplier_record,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


BASE_URL = "https://www.made-in-china.com"
TEXT_SEARCH_URL = f"{BASE_URL}/productdirectory.do"
IMAGE_UPLOAD_URL = "https://file.made-in-china.com/img-search/upload"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = (15, 60)
REMOTE_IMAGE_TIMEOUT = (10, 30)
MAX_IMAGES_PER_RUN = 20
MAX_REMOTE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_REDIRECTS = 5
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MADE_IN_CHINA_UPLOAD_EXTENSIONS = {".jpg", ".png", ".bmp"}
MAX_DECODED_IMAGE_PIXELS = 40_000_000


_temporary_directories: list[str] = []


def _cleanup_temporary_directories() -> None:
    for directory in _temporary_directories:
        shutil.rmtree(directory, ignore_errors=True)


atexit.register(_cleanup_temporary_directories)


class FetchError(RuntimeError):
    def __init__(self, message: str, *, url: str = "", body: str = "") -> None:
        super().__init__(message)
        self.url = url
        self.body = body


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_filename(value: str, fallback: str = "search") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip()).strip("._-")
    return (text[:120] or fallback).strip("._-") or fallback


def safe_int(value, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    number = max(minimum, number)
    return min(number, maximum) if maximum is not None else number


def normalize_string_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_actor_input(actor_input: dict | None) -> dict:
    result = dict(actor_input or {})
    search_mode = str(result.get("searchMode") or "keyword").strip().lower()
    if search_mode == "text":
        search_mode = "keyword"
    if search_mode not in {"keyword", "image"}:
        search_mode = "keyword"

    search_terms = normalize_string_list(result.get("searchTerms"))
    uploaded_images = result.get("uploadedImages") or []
    if not isinstance(uploaded_images, list):
        uploaded_images = []
    image_urls = normalize_string_list(result.get("imageUrls"))

    if search_mode == "keyword" and not search_terms:
        raise ValueError("Keyword search requires at least one product keyword.")

    if search_mode == "image" and not (
        uploaded_images
        or image_urls
        or normalize_string_list(result.get("searchImages"))
        or normalize_string_list(result.get("searchImageKeys"))
    ):
        raise ValueError("Image search requires at least one uploaded image or public image URL.")

    result.update(
        {
            "searchMode": search_mode,
            "searchTerms": search_terms,
            "uploadedImages": uploaded_images,
            "imageUrls": image_urls,
            "maxUniqueSuppliersPerKeyword": safe_int(
                result.get("maxUniqueSuppliersPerKeyword"), 10, 1, 500
            ),
            "maxPagesText": safe_int(result.get("maxPagesText"), 1, 1, 99),
            "maxUniqueSuppliersPerImage": safe_int(
                result.get("maxUniqueSuppliersPerImage"), 10, 1, 500
            ),
            # Made-in-China's current image UI loads at most five 20-result batches.
            "maxPagesImage": safe_int(result.get("maxPagesImage"), 1, 1, 5),
            "useApifyProxy": bool(result.get("useApifyProxy", True)),
            "includeSupplierDetails": bool(result.get("includeSupplierDetails", True)),
            "skipFailedImages": bool(result.get("skipFailedImages", True)),
            "failOnNoResults": bool(result.get("failOnNoResults", False)),
            "saveCsvFile": bool(result.get("saveCsvFile", True)),
            "csvOutputMode": str(result.get("csvOutputMode") or "combined"),
            "csvFilename": safe_filename(
                str(result.get("csvFilename") or "made_in_china_results.csv"),
                fallback="made_in_china_results.csv",
            ),
        }
    )

    if result["csvOutputMode"] not in {"combined", "separate", "both"}:
        result["csvOutputMode"] = "combined"
    if not result["csvFilename"].lower().endswith(".csv"):
        result["csvFilename"] += ".csv"

    return result


async def get_proxy_url(use_apify_proxy: bool) -> str | None:
    if not use_apify_proxy:
        return None

    try:
        proxy_configuration = await Actor.create_proxy_configuration()
        if not proxy_configuration:
            Actor.log.warning("Apify Proxy could not be initialized. Continuing without it.")
            return None
        proxy_url = await proxy_configuration.new_url()
        if proxy_url:
            Actor.log.info("Apify Proxy is enabled for Made-in-China requests.")
            return proxy_url
    except Exception as exc:
        Actor.log.warning("Apify Proxy could not be initialized. Continuing without it: %s", exc)
    return None


def build_http_session(proxy_url: str | None = None, user_agent: str | None = None) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": user_agent or DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    retry = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    if proxy_url:
        session.proxies.update({"http": proxy_url, "https": proxy_url})

    return session


def is_challenge_or_error_page(html: str) -> bool:
    text = (html or "").lower()
    markers = (
        "captcha",
        "verify you are human",
        "security verification",
        "unusual traffic",
        "access denied",
        "cf-chl-",
        "challenge-platform",
        "err_tunnel_connection_failed",
        "this site can't be reached",
    )
    return any(marker in text for marker in markers)


class MadeInChinaClient:
    def __init__(self, session: requests.Session) -> None:
        self.session = session

    def _get(self, url: str, *, params: dict | None = None) -> str:
        try:
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise FetchError(f"Request failed: {exc}", url=url) from exc

        body = response.text
        if response.status_code >= 400:
            raise FetchError(
                f"Made-in-China returned HTTP {response.status_code}.",
                url=response.url,
                body=body,
            )
        if is_challenge_or_error_page(body):
            raise FetchError("Made-in-China returned a traffic challenge or error page.", url=response.url, body=body)
        return body

    def warm_up(self) -> None:
        self._get(f"{BASE_URL}/")

    def text_search(self, term: str, page: int) -> tuple[str, str]:
        params = {
            "subaction": "hunt",
            "style": "b",
            "mode": "and",
            "code": "0",
            "comProvince": "nolimit",
            "order": "0",
            "isOpenCorrection": "1",
            "org": "top",
            "searchType": "0",
            "word": term,
            "page": page,
        }
        html = self._get(TEXT_SEARCH_URL, params=params)
        prepared = requests.Request("GET", TEXT_SEARCH_URL, params=params).prepare()
        return html, prepared.url or TEXT_SEARCH_URL

    def upload_image(self, image_path: str) -> dict:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image file does not exist: {image_path}")

        size = path.stat().st_size
        width, height = image_dimensions(path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = {
            "orgwidth": str(width),
            "orgheight": str(height),
            "zipsize": str(size),
            "orgsize": str(size),
            "uploadMethod": "1",
            "detailedError": "true",
        }

        try:
            with path.open("rb") as image_file:
                response = self.session.post(
                    IMAGE_UPLOAD_URL,
                    params={"lan": "en"},
                    files={"multipartFile": (path.name, image_file, mime_type)},
                    data=data,
                    timeout=REQUEST_TIMEOUT,
                )
        except requests.RequestException as exc:
            raise FetchError(f"Image upload failed: {exc}", url=IMAGE_UPLOAD_URL) from exc

        if response.status_code >= 400:
            raise FetchError(
                f"Image upload returned HTTP {response.status_code}.",
                url=response.url,
                body=response.text,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FetchError("Image upload did not return JSON.", url=response.url, body=response.text) from exc

        data_payload = payload.get("data") if isinstance(payload, dict) else None
        if payload.get("code") != 200 or not isinstance(data_payload, dict):
            raise FetchError(
                f"Image upload was rejected: {payload.get('msg') or 'unknown response'}",
                url=response.url,
                body=response.text,
            )

        search_url = normalize_mic_url(str(data_payload.get("url") or ""))
        search_id = clean_text(str(data_payload.get("id") or ""))
        if not search_id:
            match = re.search(r"/img-search/([A-Za-z0-9]+)\.html", search_url)
            search_id = match.group(1) if match else ""
        if not search_url or not search_id:
            raise FetchError("Image upload succeeded but did not return a search URL and ID.", body=response.text)

        return {
            "id": search_id,
            "url": search_url,
            "uploaded_image_url": normalize_mic_url(str(data_payload.get("imgUrl") or "")),
        }

    def image_results(self, upload: dict, page: int) -> tuple[str, str]:
        if page == 1:
            url = str(upload["url"])
            return self._get(url), url

        url = f"{BASE_URL}/img-search/ajax/{upload['id']}"
        params = {
            "sourceType": "0",
            "uploadMethod": "1",
            "leafCode": "",
            "colorCode": "",
            "page": page,
        }
        html = self._get(url, params=params)
        prepared = requests.Request("GET", url, params=params).prepare()
        return html, prepared.url or url

    def supplier_profile(self, profile_url: str) -> str:
        return self._get(profile_url)


def image_dimensions(path: Path) -> tuple[int, int]:
    """Read common image dimensions without adding a heavy image dependency."""
    try:
        with path.open("rb") as file:
            head = file.read(32)
            if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
                return struct.unpack(">II", head[16:24])
            if head.startswith((b"GIF87a", b"GIF89a")) and len(head) >= 10:
                return struct.unpack("<HH", head[6:10])
            if head.startswith(b"BM") and len(head) >= 26:
                return struct.unpack("<II", head[18:26])
            if head.startswith(b"\xff\xd8"):
                file.seek(2)
                while True:
                    marker_start = file.read(1)
                    if not marker_start:
                        break
                    if marker_start != b"\xff":
                        continue
                    marker = file.read(1)
                    while marker == b"\xff":
                        marker = file.read(1)
                    if marker in {bytes([value]) for value in range(0xC0, 0xC4)} | {
                        bytes([value]) for value in range(0xC5, 0xC8)
                    } | {bytes([value]) for value in range(0xC9, 0xCC)} | {
                        bytes([value]) for value in range(0xCD, 0xD0)
                    }:
                        length = struct.unpack(">H", file.read(2))[0]
                        segment = file.read(length - 2)
                        if len(segment) >= 5:
                            height, width = struct.unpack(">HH", segment[1:5])
                            return width, height
                        break
                    length_data = file.read(2)
                    if len(length_data) != 2:
                        break
                    length = struct.unpack(">H", length_data)[0]
                    file.seek(max(0, length - 2), 1)
    except (OSError, ValueError, struct.error):
        pass
    return 0, 0


def _is_http_url(value: str) -> bool:
    try:
        return urlparse(value).scheme.lower() in {"http", "https"}
    except Exception:
        return False


def _validate_public_image_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Image URL must use HTTP or HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("Image URLs containing credentials are not allowed.")
    if not parsed.hostname:
        raise ValueError("Image URL must include a hostname.")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Could not resolve image hostname {parsed.hostname!r}.") from exc
    if not addresses:
        raise ValueError(f"Could not resolve image hostname {parsed.hostname!r}.")
    for address in addresses:
        ip_value = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip_value.is_global:
            raise ValueError("Image URL resolves to a private or non-public network address.")
    return parsed.geturl()


def _detect_image_extension(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if content.startswith(b"BM"):
        return ".bmp"
    return None


def _write_uploadable_image(content: bytes, destination: Path, stem: str) -> str:
    """Write an image in a format accepted by Made-in-China's upload endpoint."""
    extension = _detect_image_extension(content)
    if not extension:
        raise ValueError("File is not a supported JPG, PNG, GIF, WebP, or BMP image.")

    safe_stem = safe_filename(stem, "product_image")
    if extension in MADE_IN_CHINA_UPLOAD_EXTENSIONS:
        output_path = destination / f"{safe_stem}{extension}"
        output_path.write_bytes(content)
        return str(output_path)

    try:
        with Image.open(io.BytesIO(content)) as source_image:
            source_image.seek(0)
            source_image = ImageOps.exif_transpose(source_image)
            width, height = source_image.size
            if width < 1 or height < 1 or width * height > MAX_DECODED_IMAGE_PIXELS:
                raise ValueError("Image dimensions are invalid or too large to convert safely.")

            source_image.load()
            if source_image.mode in {"RGBA", "LA"} or (
                source_image.mode == "P" and "transparency" in source_image.info
            ):
                rgba_image = source_image.convert("RGBA")
                converted_image = Image.new("RGB", rgba_image.size, "white")
                converted_image.paste(rgba_image, mask=rgba_image.getchannel("A"))
            else:
                converted_image = source_image.convert("RGB")

            output_path = destination / f"{safe_stem}.jpg"
            converted_image.save(output_path, format="JPEG", quality=92, optimize=True)
    except (OSError, SyntaxError) as exc:
        raise ValueError("Image could not be decoded for upload.") from exc

    if output_path.stat().st_size > MAX_REMOTE_IMAGE_BYTES:
        output_path.unlink(missing_ok=True)
        raise ValueError("Converted image exceeds the 20 MB limit.")
    return str(output_path)


def _download_remote_image(url: str, destination: Path, index: int) -> str:
    current_url = _validate_public_image_url(url)
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "image/jpeg,image/png,image/bmp;q=0.9,image/*;q=0.5,*/*;q=0.1",
        }
    )

    try:
        for _ in range(MAX_IMAGE_REDIRECTS + 1):
            with session.get(
                current_url,
                allow_redirects=False,
                stream=True,
                timeout=REMOTE_IMAGE_TIMEOUT,
            ) as response:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Image URL redirected without a destination.")
                    current_url = _validate_public_image_url(urljoin(current_url, location))
                    continue

                response.raise_for_status()
                length = response.headers.get("Content-Length")
                if length and length.isdigit() and int(length) > MAX_REMOTE_IMAGE_BYTES:
                    raise ValueError("Remote image exceeds the 20 MB limit.")

                content = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    content.extend(chunk)
                    if len(content) > MAX_REMOTE_IMAGE_BYTES:
                        raise ValueError("Remote image exceeds the 20 MB limit.")

                source_name = Path(urlparse(current_url).path).name
                source_stem = Path(source_name).stem if source_name else f"remote_image_{index}"
                return _write_uploadable_image(
                    bytes(content),
                    destination,
                    f"{index:02d}_{safe_filename(source_stem, 'remote_image')}",
                )

        raise ValueError(f"Remote image exceeded {MAX_IMAGE_REDIRECTS} redirects.")
    finally:
        session.close()


def _extract_uploaded_image_reference(uploaded_item) -> str | None:
    if isinstance(uploaded_item, str):
        return normalize_image_reference(uploaded_item) or None
    if not isinstance(uploaded_item, dict):
        return None
    reference = str(
        uploaded_item.get("url")
        or uploaded_item.get("key")
        or uploaded_item.get("id")
        or uploaded_item.get("name")
        or uploaded_item.get("filename")
        or uploaded_item.get("fileName")
        or ""
    ).strip()
    return normalize_image_reference(reference) or None


def _record_to_bytes(record, key: str) -> bytes:
    if isinstance(record, (bytes, bytearray)):
        return bytes(record)
    if isinstance(record, str):
        return record.encode("utf-8")
    raise ValueError(f"Key-value store image {key!r} was not binary content.")


async def _read_kv_image_with_fallback(default_kv, key: str):
    candidates = [key]
    if Path(key).suffix.lower() not in IMAGE_EXTENSIONS:
        candidates.extend(f"{key}{extension}" for extension in IMAGE_EXTENSIONS)
    if key != "query-image-1":
        candidates.append("query-image-1")

    for candidate in list(dict.fromkeys(candidates)):
        try:
            record = await default_kv.get_value(candidate)
        except Exception as exc:
            Actor.log.warning("Could not read uploaded-image key %s: %s", candidate, exc)
            continue
        if record:
            return candidate, record
    return None, None


async def resolve_input_images(actor_input: dict) -> list[str]:
    local_paths = normalize_string_list(actor_input.get("searchImages"))
    image_urls = [normalize_image_reference(value) for value in actor_input.get("imageUrls", [])]
    image_keys = normalize_string_list(actor_input.get("searchImageKeys"))
    skip_failed = bool(actor_input.get("skipFailedImages", True))

    for uploaded_item in actor_input.get("uploadedImages", []) or []:
        reference = _extract_uploaded_image_reference(uploaded_item)
        if not reference:
            continue
        if _is_http_url(reference):
            image_urls.append(reference)
        else:
            image_keys.append(reference)

    image_urls = list(dict.fromkeys(value for value in image_urls if value))
    image_keys = list(dict.fromkeys(value for value in image_keys if value))
    if len(local_paths) + len(image_urls) + len(image_keys) > MAX_IMAGES_PER_RUN:
        raise ValueError(f"A maximum of {MAX_IMAGES_PER_RUN} images is supported per run.")

    image_directory = Path(tempfile.mkdtemp(prefix="made_in_china_images_"))
    _temporary_directories.append(str(image_directory))
    resolved: list[str] = []

    for path in local_paths:
        if Path(path).is_file():
            try:
                local_path = Path(path)
                content = local_path.read_bytes()
                if len(content) > MAX_REMOTE_IMAGE_BYTES:
                    raise ValueError("Local image exceeds the 20 MB limit.")
                output_path = _write_uploadable_image(
                    content,
                    image_directory,
                    f"local_{len(resolved) + 1:02d}_{local_path.stem}",
                )
                resolved.append(output_path)
            except Exception as exc:
                Actor.log.warning("Local image failed and was skipped: %s (%s)", path, exc)
                if not skip_failed:
                    raise
        elif skip_failed:
            Actor.log.warning("Local image path does not exist and was skipped: %s", path)
        else:
            raise FileNotFoundError(f"Local image path does not exist: {path}")

    for index, image_url in enumerate(image_urls, start=1):
        try:
            output_path = await asyncio.to_thread(_download_remote_image, image_url, image_directory, index)
            resolved.append(output_path)
            Actor.log.info("Downloaded public image URL: %s", image_url)
        except Exception as exc:
            Actor.log.warning("Public image URL failed and was skipped: %s (%s)", image_url, exc)
            if not skip_failed:
                raise

    if image_keys:
        default_kv = await Actor.open_key_value_store()
        for key in image_keys:
            try:
                resolved_key, record = await _read_kv_image_with_fallback(default_kv, key)
                if not record:
                    raise FileNotFoundError(f"No uploaded image was found for key {key!r}.")
                content = _record_to_bytes(record, resolved_key or key)
                if len(content) > MAX_REMOTE_IMAGE_BYTES:
                    raise ValueError("Uploaded image exceeds the 20 MB limit.")
                output_path = _write_uploadable_image(
                    content,
                    image_directory,
                    safe_filename(Path(resolved_key or key).stem, "uploaded_image"),
                )
                resolved.append(output_path)
                Actor.log.info("Loaded uploaded image: %s", resolved_key or key)
            except Exception as exc:
                Actor.log.warning("Uploaded image %s failed and was skipped: %s", key, exc)
                if not skip_failed:
                    raise

    Actor.log.info("Resolved %s image file(s) for Made-in-China image search.", len(resolved))
    return resolved


async def save_debug_text(prefix: str, content: str, content_type: str = "text/html") -> None:
    if not content:
        return
    key = f"{safe_filename(prefix, 'debug')}_debug.html"
    await Actor.set_value(key, content, content_type=content_type)
    Actor.log.warning("Saved diagnostic response to key-value store: %s", key)


def _upsert_records(
    records: list[dict],
    suppliers_by_key: dict[str, dict],
    seen_for_input: set[str],
    search_input: str,
    search_type: str,
    max_unique_for_input: int,
) -> int:
    created = 0
    for record in records:
        key = key_for_dedupe(
            str(record.get("vendor_name") or ""),
            str(record.get("vendor_profile_url") or ""),
            str(record.get("product_url") or ""),
        )
        if not key:
            continue
        _, was_created = upsert_supplier_record(
            suppliers_by_key,
            seen_for_input,
            key,
            record,
            search_input,
            search_type,
            max_unique_for_input,
        )
        if was_created:
            created += 1
    return created


async def run_keyword_searches(
    client: MadeInChinaClient,
    actor_input: dict,
    suppliers_by_key: dict[str, dict],
) -> dict:
    summary: dict[str, dict] = {}
    limit = actor_input["maxUniqueSuppliersPerKeyword"]
    max_pages = actor_input["maxPagesText"]

    for term in actor_input["searchTerms"]:
        Actor.log.info("[KEYWORD SEARCH] %s", term)
        seen_for_term: set[str] = set()
        rank_offset = 0
        pages_processed = 0
        status = "completed"

        for page in range(1, max_pages + 1):
            html = ""
            try:
                html, _ = client.text_search(term, page)
                records = parse_text_search_html(html, result_page=page, rank_offset=rank_offset)
                if not records:
                    await save_debug_text(f"keyword_{term}_page_{page}", html)
                    Actor.log.warning("No product cards were found for keyword %r on page %s.", term, page)
                    status = "no_results" if page == 1 else "completed"
                    break
            except FetchError as exc:
                await save_debug_text(f"keyword_{term}_page_{page}", exc.body)
                Actor.log.warning("Keyword search failed for %r on page %s: %s", term, page, exc)
                status = "failed"
                if actor_input["failOnNoResults"]:
                    raise
                break

            pages_processed += 1
            created = _upsert_records(records, suppliers_by_key, seen_for_term, term, "keyword", limit)
            rank_offset += len(records)
            Actor.log.info(
                "[KEYWORD SEARCH] Page %s: %s cards, %s new global suppliers, %s/%s suppliers for this keyword.",
                page,
                len(records),
                created,
                len(seen_for_term),
                limit,
            )
            if len(seen_for_term) >= limit or len(records) < 10:
                break

        summary[term] = {
            "status": status,
            "pages_processed": pages_processed,
            "unique_suppliers": len(seen_for_term),
        }

    return summary


async def run_image_searches(
    client: MadeInChinaClient,
    actor_input: dict,
    suppliers_by_key: dict[str, dict],
) -> dict:
    summary: dict[str, dict] = {}
    image_paths = await resolve_input_images(actor_input)
    limit = actor_input["maxUniqueSuppliersPerImage"]
    max_pages = actor_input["maxPagesImage"]

    for image_path in image_paths:
        search_input = Path(image_path).name
        Actor.log.info("[IMAGE SEARCH] %s", search_input)
        seen_for_image: set[str] = set()
        rank_offset = 0
        pages_processed = 0
        status = "completed"
        upload: dict | None = None

        try:
            upload = client.upload_image(image_path)
            Actor.log.info("[IMAGE SEARCH] Upload succeeded with search ID %s.", upload["id"])
        except (FetchError, OSError, ValueError) as exc:
            if isinstance(exc, FetchError):
                await save_debug_text(f"image_{search_input}_upload", exc.body, "text/plain")
            Actor.log.warning("Image upload failed for %s: %s", search_input, exc)
            status = "failed"
            summary[search_input] = {
                "status": status,
                "pages_processed": 0,
                "unique_suppliers": 0,
            }
            if not actor_input["skipFailedImages"]:
                raise
            continue

        for page in range(1, max_pages + 1):
            try:
                html, _ = client.image_results(upload, page)
                records = parse_image_search_html(html, result_page=page, rank_offset=rank_offset)
                if not records:
                    await save_debug_text(f"image_{search_input}_page_{page}", html)
                    Actor.log.warning("No image-search cards were found for %s on batch %s.", search_input, page)
                    status = "no_results" if page == 1 else "completed"
                    break
            except FetchError as exc:
                await save_debug_text(f"image_{search_input}_page_{page}", exc.body)
                Actor.log.warning("Image results failed for %s on batch %s: %s", search_input, page, exc)
                status = "failed"
                if not actor_input["skipFailedImages"]:
                    raise
                break

            pages_processed += 1
            created = _upsert_records(records, suppliers_by_key, seen_for_image, search_input, "image", limit)
            rank_offset += len(records)
            total_count = parse_total_count(html)
            Actor.log.info(
                "[IMAGE SEARCH] Batch %s: %s cards, %s new global suppliers, %s/%s suppliers for this image.",
                page,
                len(records),
                created,
                len(seen_for_image),
                limit,
            )
            if len(seen_for_image) >= limit or len(records) < 20:
                break
            if total_count is not None and rank_offset >= total_count:
                break

        summary[search_input] = {
            "status": status,
            "pages_processed": pages_processed,
            "unique_suppliers": len(seen_for_image),
            "image_search_id": upload["id"],
        }

    return summary


async def enrich_supplier_profiles(client: MadeInChinaClient, rows: list[dict]) -> dict:
    enriched = 0
    failed = 0
    cache: dict[str, dict] = {}

    for index, row in enumerate(rows, start=1):
        profile_url = str(row.get("vendor_profile_url") or "")
        if not profile_url:
            continue
        try:
            if profile_url not in cache:
                html = client.supplier_profile(profile_url)
                cache[profile_url] = parse_supplier_profile_html(html)
            details = cache[profile_url]
            if details:
                apply_supplier_details(row, details)
                enriched += 1
            Actor.log.info("[SUPPLIER DETAILS] %s/%s %s", index, len(rows), row.get("vendor_name"))
        except FetchError as exc:
            failed += 1
            Actor.log.warning("Supplier details could not be loaded for %s: %s", profile_url, exc)

    return {"enriched": enriched, "failed": failed}


def _csv_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return ""
    return value


def rows_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})
    return output.getvalue()


def rows_by_search_input(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        inputs = row.get("matched_search_inputs") or [row.get("search_input")]
        for search_input in inputs:
            if not search_input:
                continue
            matches = [
                match
                for match in row.get("matched_products") or []
                if match.get("search_input") == search_input
            ]
            output_row = dict(row)
            output_row["search_input"] = search_input
            output_row["matched_search_inputs"] = [search_input]
            output_row["matched_products"] = matches
            if matches:
                output_row["search_type"] = matches[0].get("search_type")
                for field in PRODUCT_MATCH_FIELDS:
                    output_row[field] = matches[0].get(field)
            grouped.setdefault(str(search_input), []).append(output_row)
    return grouped


async def save_csv_outputs(rows: list[dict], filename: str, mode: str) -> None:
    if mode in {"combined", "both"}:
        await Actor.set_value(filename, rows_to_csv(rows), content_type="text/csv")
    if mode in {"separate", "both"}:
        used_names: set[str] = set()
        for search_input, group_rows in rows_by_search_input(rows).items():
            base = safe_filename(search_input)
            candidate = f"{base}.csv"
            counter = 2
            while candidate in used_names:
                candidate = f"{base}_{counter}.csv"
                counter += 1
            used_names.add(candidate)
            await Actor.set_value(candidate, rows_to_csv(group_rows), content_type="text/csv")


async def main() -> None:
    async with Actor:
        actor_input = normalize_actor_input(await Actor.get_input())
        if actor_input["searchMode"] == "image":
            image_input_count = sum(
                len(actor_input.get(field) or [])
                for field in ("imageUrls", "uploadedImages", "searchImages", "searchImageKeys")
            )
            Actor.log.info("Starting image search with %s image input(s).", image_input_count)
        else:
            Actor.log.info(
                "Starting keyword search with %s keyword input(s).",
                len(actor_input["searchTerms"]),
            )

        proxy_url = await get_proxy_url(actor_input["useApifyProxy"])
        session = build_http_session(proxy_url=proxy_url)
        client = MadeInChinaClient(session)
        suppliers_by_key: dict[str, dict] = {}
        run_summary: dict = {
            "search_mode": actor_input["searchMode"],
            "inputs": {},
            "supplier_details": {"enriched": 0, "failed": 0},
        }

        try:
            client.warm_up()
            if actor_input["searchMode"] == "image":
                run_summary["inputs"] = await run_image_searches(client, actor_input, suppliers_by_key)
            else:
                run_summary["inputs"] = await run_keyword_searches(client, actor_input, suppliers_by_key)

            rows = list(suppliers_by_key.values())
            if rows and actor_input["includeSupplierDetails"]:
                run_summary["supplier_details"] = await enrich_supplier_profiles(client, rows)

            for row in rows:
                await Actor.push_data(row)

            if rows and actor_input["saveCsvFile"]:
                await save_csv_outputs(rows, actor_input["csvFilename"], actor_input["csvOutputMode"])

            run_summary["unique_suppliers"] = len(rows)
            run_summary["matched_products"] = sum(len(row.get("matched_products") or []) for row in rows)
            await Actor.set_value("RUN_SUMMARY.json", run_summary, content_type="application/json")

            if not rows:
                message = (
                    "No Made-in-China supplier results were found. The site may have returned no matches "
                    "or a traffic challenge; check RUN_SUMMARY.json and diagnostic HTML files."
                )
                if actor_input["failOnNoResults"]:
                    raise RuntimeError(message)
                Actor.log.warning(message)

            Actor.log.info("Finished successfully with %s unique supplier row(s).", len(rows))
        finally:
            session.close()


if __name__ == "__main__":
    logging.info("Launching Made-in-China Product & Supplier Finder process.")
    if not os.environ.get("ACTOR_STARTUP_CHECK"):
        asyncio.run(main())
