from src.utils.log_sanitizer import sanitize_url_for_log


def test_sanitize_url_for_log_hides_query_string():
    raw_url = "https://javdb.com/search?q=SSIS-123&f=all"

    sanitized = sanitize_url_for_log(raw_url)

    assert "q=SSIS-123" not in sanitized
    assert "f=all" not in sanitized
    assert "search_url_hash=" in sanitized
    assert "https://javdb.com/search" in sanitized
