"""
shiroutowiki.work 專用爬蟲
只負責查詢作品頁並提取女優名稱與最小必要中繼資料。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from src.utils.log_sanitizer import sanitize_url_for_log
logger = logging.getLogger(__name__)


class ShiroutoWikiScraper:
    """素人女優 wiki 獨立搜尋器。"""

    BASE_URL = "https://shiroutowiki.work"

    def __init__(self, safe_searcher, headers: dict[str, str], timeout: int = 20):
        self.safe_searcher = safe_searcher
        self.headers = headers
        self.timeout = timeout

    @staticmethod
    def _append_unique(candidates: list[str], value: str | None) -> None:
        if value and value not in candidates:
            candidates.append(value)

    @classmethod
    def build_search_candidates(cls, code: str) -> list[str]:
        """建立 shiroutowiki 專用搜尋候選。

        順序：
        1. 原始番號
        2. 去符號番號
        3. 可安全推導的 FANZA 配信品番
        """
        normalized = code.strip()
        if not normalized:
            return []

        candidates: list[str] = []
        cls._append_unique(candidates, normalized)

        compact = re.sub(r"[^A-Za-z0-9]", "", normalized)
        if compact and compact != normalized:
            cls._append_unique(candidates, compact)

        delivery_code = cls._derive_delivery_code(normalized)
        cls._append_unique(candidates, delivery_code)
        return candidates

    @staticmethod
    def _derive_delivery_code(code: str) -> str | None:
        """推導可安全猜測的 FANZA 配信品番。

        規則：
        - 英文-3碼：補成 5 碼，例如 SNOS-045 -> snos00045
        - 英文-5碼：直接轉為小寫 delivery code，例如 MIDV-00567 -> midv00567
        - 4 碼不主動推導，避免誤判。
        """
        match = re.match(r"^([A-Z]{2,10})-(\d+)$", code.upper())
        if not match:
            return None

        prefix, digits = match.groups()
        if len(digits) == 3:
            return f"{prefix.lower()}{digits.zfill(5)}"
        if len(digits) == 5:
            return f"{prefix.lower()}{digits}"
        return None

    @staticmethod
    def _compact_code(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"[^a-z0-9]", "", value.lower())

    @staticmethod
    def _normalize_detail_map(soup: BeautifulSoup) -> dict[str, str]:
        fields: dict[str, str] = {}
        for dt in soup.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            label = dt.get_text(" ", strip=True)
            value = dd.get_text(" ", strip=True)
            if label:
                fields[label] = value
        return fields

    def _fetch_soup(self, url: str) -> BeautifulSoup | None:
        """取得網頁並轉為 BeautifulSoup。"""

        def make_request(target_url, headers=None):
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(target_url, headers=headers or self.headers)
                response.raise_for_status()
                return BeautifulSoup(response.text, "html.parser")

        try:
            return self.safe_searcher.safe_request(
                make_request, url, headers=self.headers
            )
        except Exception as e:
            logger.warning(
                f"⚠️ shiroutowiki 取得頁面失敗 {sanitize_url_for_log(url)}: {e}"
            )
            return None

    def _parse_search_rows(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for tr in soup.select("table tbody tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue

            detail_link = cells[0].find("a", href=True)
            actress_links = cells[2].find_all("a")
            actresses = [
                link.get_text(strip=True)
                for link in actress_links
                if link.get_text(strip=True)
            ]
            row_code = cells[3].get_text(" ", strip=True)
            title_link = cells[1].find("a", href=True)
            title = cells[1].get_text(" ", strip=True)

            rows.append(
                {
                    "detail_url": (
                        urljoin(self.BASE_URL, detail_link["href"])
                        if detail_link
                        else None
                    ),
                    "title": title,
                    "row_code": row_code,
                    "actresses": actresses,
                    "title_url": title_link["href"] if title_link else None,
                }
            )

        return rows

    def _parse_detail_page(self, soup: BeautifulSoup, detail_url: str) -> dict[str, Any]:
        fields = self._normalize_detail_map(soup)
        actress_dd = None
        for dt in soup.find_all("dt"):
            if dt.get_text(" ", strip=True) == "女優名":
                actress_dd = dt.find_next_sibling("dd")
                break

        actresses: list[str] = []
        if actress_dd:
            actress_links = actress_dd.find_all("a")
            actresses = [
                link.get_text(strip=True)
                for link in actress_links
                if link.get_text(strip=True)
            ]
            if not actresses:
                raw_text = actress_dd.get_text(" ", strip=True)
                if raw_text:
                    actresses = [raw_text]

        title = fields.get("タイトル")
        if not title:
            title_element = soup.find("h1")
            if title_element:
                title = title_element.get_text(" ", strip=True)

        return {
            "actresses": actresses,
            "title": title,
            "product_code": fields.get("商品品番"),
            "delivery_code": fields.get("配信品番"),
            "search_url": detail_url,
        }

    def _matches_detail(
        self, detail: dict[str, Any], allowed_compact_codes: set[str]
    ) -> bool:
        product_code = self._compact_code(detail.get("product_code"))
        delivery_code = self._compact_code(detail.get("delivery_code"))
        return (
            product_code in allowed_compact_codes
            or delivery_code in allowed_compact_codes
        )

    def _build_direct_detail_url(self, candidate: str) -> str | None:
        if re.fullmatch(r"[a-z]{2,10}\d{5}", candidate):
            return f"{self.BASE_URL}/fanza-video/{candidate.lower()}/"
        return None

    def search_video(
        self,
        code: str,
        search_candidates: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """搜尋單一番號，回傳最小資料集。"""
        candidates = search_candidates or self.build_search_candidates(code)
        allowed_compact_codes = self._build_allowed_compact_codes(code, candidates)

        for candidate in candidates:
            search_url = f"{self.BASE_URL}/?s={quote(candidate)}"
            soup = self._fetch_soup(search_url)
            if not soup:
                continue

            rows = self._parse_search_rows(soup)
            logger.debug(
                f"🔍 shiroutowiki 搜尋 {candidate}: 取得 {len(rows)} 筆搜尋列"
            )

            matched_result = self._find_matching_result(
                rows,
                allowed_compact_codes,
                search_url,
                candidate,
            )
            if matched_result:
                return matched_result

            direct_detail_url = self._build_direct_detail_url(candidate)
            if direct_detail_url:
                detail_soup = self._fetch_soup(direct_detail_url)
                if not detail_soup:
                    continue
                detail = self._parse_detail_page(detail_soup, direct_detail_url)
                if self._matches_detail(detail, allowed_compact_codes):
                    return self._build_detail_result(
                        detail,
                        direct_detail_url,
                        candidate,
                    )

        logger.info(f"番號 {code} 未在 shiroutowiki 中找到女優資訊")
        return None

    def _build_allowed_compact_codes(
        self, code: str, candidates: list[str]
    ) -> set[str]:
        allowed_compact_codes = {
            self._compact_code(candidate) for candidate in candidates if candidate
        }
        allowed_compact_codes.add(self._compact_code(code))
        return allowed_compact_codes

    def _build_detail_result(
        self,
        detail: dict[str, Any],
        detail_url: str,
        candidate: str,
        row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "source": "shiroutowiki",
            "actresses": detail.get("actresses", []),
            "title": detail.get("title") or (row or {}).get("title"),
            "search_url": detail_url,
            "matched_code": detail.get("product_code")
            or detail.get("delivery_code")
            or (row or {}).get("row_code")
            or candidate,
            "delivery_code": detail.get("delivery_code"),
            "product_code": detail.get("product_code"),
        }

    def _find_matching_result(
        self,
        rows: list[dict[str, Any]],
        allowed_compact_codes: set[str],
        search_url: str,
        candidate: str,
    ) -> dict[str, Any] | None:
        for row in rows:
            detail_result = self._find_matching_detail_for_row(
                row,
                allowed_compact_codes,
                candidate,
            )
            if detail_result:
                return detail_result

            row_result = self._find_matching_row_result_for_row(
                row,
                allowed_compact_codes,
                search_url,
                candidate,
            )
            if row_result:
                return row_result

        return None

    def _find_matching_detail_result(
        self,
        rows: list[dict[str, Any]],
        allowed_compact_codes: set[str],
        candidate: str,
    ) -> dict[str, Any] | None:
        for row in rows:
            detail_result = self._find_matching_detail_for_row(
                row,
                allowed_compact_codes,
                candidate,
            )
            if detail_result:
                return detail_result

        return None

    def _find_matching_detail_for_row(
        self,
        row: dict[str, Any],
        allowed_compact_codes: set[str],
        candidate: str,
    ) -> dict[str, Any] | None:
        detail_url = row.get("detail_url")
        if not detail_url:
            return None

        detail_soup = self._fetch_soup(detail_url)
        if not detail_soup:
            return None

        detail = self._parse_detail_page(detail_soup, detail_url)
        if self._matches_detail(detail, allowed_compact_codes):
            return self._build_detail_result(detail, detail_url, candidate, row)

        return None

    def _find_matching_row_result(
        self,
        rows: list[dict[str, Any]],
        allowed_compact_codes: set[str],
        search_url: str,
        candidate: str,
    ) -> dict[str, Any] | None:
        for row in rows:
            row_result = self._find_matching_row_result_for_row(
                row,
                allowed_compact_codes,
                search_url,
                candidate,
            )
            if row_result:
                return row_result

        return None

    def _find_matching_row_result_for_row(
        self,
        row: dict[str, Any],
        allowed_compact_codes: set[str],
        search_url: str,
        candidate: str,
    ) -> dict[str, Any] | None:
        row_code = self._compact_code(row.get("row_code"))
        if row_code not in allowed_compact_codes or not row.get("actresses"):
            return None

        detail_url = row.get("detail_url")
        return {
            "source": "shiroutowiki",
            "actresses": row.get("actresses", []),
            "title": row.get("title"),
            "search_url": detail_url or search_url,
            "matched_code": row.get("row_code") or candidate,
            "delivery_code": row.get("row_code"),
            "product_code": None,
        }
