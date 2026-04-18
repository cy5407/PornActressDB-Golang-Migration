import hashlib
from urllib.parse import urlparse


def sanitize_url_for_log(url: str) -> str:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else url
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{base} search_url_hash={digest}"
