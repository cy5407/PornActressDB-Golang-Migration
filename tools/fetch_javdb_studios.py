"""
JAVDB 片商番號前綴爬蟲
執行方式: python tools/fetch_javdb_studios.py
輸出結果會印在終端機，並寫入 tools/javdb_studio_codes.json
"""

import re
import time
import json
import sys

try:
    from curl_cffi import requests
except ImportError:
    print("請先安裝 curl-cffi: pip install curl-cffi")
    sys.exit(1)

# ── Cookie（從瀏覽器複製） ────────────────────────────────────────────────────
COOKIE = (
    "locale=zh; _ym_uid=1773240164777340516; _ym_d=1773240164; over18=1; "
    "remember_me_token=eyJfcmFpbHMiOnsibWVzc2FnZSI6IkluUnlkRkpVY0RWNE9VSkNOMTl1UnpSbVRGSTVJZz09IiwiZXhwIjoiMjAyNi0wNC0wNlQxNToyOTowNS4wMDBaIiwicHVyIjoiY29va2llLnJlbWVtYmVyX21lX3Rva2VuIn19--a66a916bcb89fe4dac77ec658ae2c802d576e559; "
    "list_mode=v; theme=dark; _ym_isad=1; "
    "cf_clearance=PV1S45bMtIvHZrV3eul29lOecUTCnOgUlw5qZDtLgMc-1775461079-1.2.1.1-0DL91ImQr7qTs3GnLTBylRVMt.tKghz3tXEqg1EbbF1OeMgxFV3BCrSyMj_sgjv8T_E51Mm3pIjNAIUy3kB6SXHwKGVb3D1nhJvOVRODEd92P5QVbbs0670_7I.YQriORv8jPr5zlDJbSOg6Q1QpMpB8CcE9cuqOImjahkCNemf37Kgkpt_hFYkzio2gWUMu85k8VQAlsmBp5Hvm2K5sKBBo.CkyeOt4PZ3FhpmuVkWCYhkEpM71240Efrus4GqRjzqPxo4UoSaXNZUR.joUMGkT.czJViMGHAi60RaabPfOYYDShzwEAyNZgI_Q8aqGxtL4.quuUebGL9SUnMbP9w; "
    "_jdb_session=brisHfBDy6R66%2BcPW12LP%2ByOryxEBv%2Bze416NgWMk48LIYbnfSUxS6tWzlv88ujsEaD%2BxiO5QLFB547%2BlvlqNP39y8XZNNL5wg1H5BHhDO9Le%2BgclnY9cyJE%2BsVRErd1PZfp3tmT7umH5QnKRpLuyTrd8cw2nbjnldSDzdu3gfpzpQw6Ft7k%2Fj8JvvppkQy0mbD%2FWOMhFlaSoI5Jbz3rGtAd89KCIvJfH0Y%2Fe7%2FACiS%2FP26G0mlN3BTlWmJt61QM6%2Fei26D3Uk0pOEODmM%2F112ecQ%2BI7Te1ettclkNeoHZ%2FnWLD3hue44iSms8ZkLKtdwCORyxG%2BOpjZC8mLDVrnk7r3NcefWXZ0qNlqgG7jIMWXu5SxOH1SoA0rdI4wQwgx%2FLw%3D--QwF01Nzn5mMoW3XP--Zb5o%2FEwi7z6IltE7J29qQw%3D%3D"
)
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://javdb.com/",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "Cookie": COOKIE,
}

# 透過已知番號來查對應的片商 maker ID（全部已確認）
STUDIOS_LOOKUP = {
    "MOODYZ":    ("zKW",  None),
    "S1":        ("7R",   None),
    "ATTACKERS": ("Ywz",  None),
    "E-BODY":    ("bgA",  None),
    "FALENO":    ("Y46",  None),
    "FITCH":     ("Aby",  None),
    "KAWAII":    ("rmZ",  None),
    "MADONNA":   ("35e",  None),
    "PREMIUM":   ("ZXX",  None),
    "PRESTIGE":  ("6M",   None),
    "SOD":       ("q6",   None),
}

session = requests.Session(impersonate="chrome124")
session.headers.update(HEADERS)


# 排除清單：JAVDB 頁面固定出現的非片商路徑
_MAKER_ID_EXCLUDE = {"uncensored", "censored", "western", "index", "search"}

def find_maker_id_via_video(video_code: str) -> str | None:
    """透過已知番號查詢該影片頁面，從中抓出片商 maker ID"""
    search_url = f"https://javdb.com/search?q={video_code}&f=all"
    try:
        resp = session.get(search_url, timeout=15)
        if resp.status_code != 200:
            return None
        # 找影片連結 /v/XXXXX
        video_ids = re.findall(r'href="/v/([A-Za-z0-9]+)"', resp.text)
        if not video_ids:
            return None
        # 進入第一個影片頁面
        video_url = f"https://javdb.com/v/{video_ids[0]}"
        time.sleep(1)
        resp2 = session.get(video_url, timeout=15)
        if resp2.status_code != 200:
            return None
        # 從影片頁面找 maker 連結，過濾掉已知非 ID 的字串
        # 片商 ID 通常是 2~5 個英數字元
        maker_matches = re.findall(r'href="/makers/([A-Za-z0-9]{2,5})"', resp2.text)
        for m in maker_matches:
            if m.lower() not in _MAKER_ID_EXCLUDE:
                return m
        return None
    except Exception as e:
        print(f"    查詢失敗: {e}")
        return None


def extract_codes(html: str) -> list:
    codes = re.findall(r'[A-Z]{2,6}-\d{2,5}', html)
    prefixes = sorted(set(
        m.group(1) for c in codes
        for m in [re.match(r'^([A-Z]+)', c)] if m
    ))
    return prefixes


def fetch_studio(name: str, maker_id: str) -> list:
    url = f"https://javdb.com/makers/{maker_id}?f=download"
    print(f"  爬取 {name} ...")
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  FAIL {name}: HTTP {resp.status_code}")
            return []
        if "Cloudflare" in resp.text or "blocked" in resp.text.lower():
            print(f"  FAIL {name}: Cloudflare 擋住")
            return []
        codes = extract_codes(resp.text)
        print(f"  OK   {name}: {len(codes)} 個前綴 -> {codes}")
        return codes
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        return []


def main():
    print("=== JAVDB 片商番號前綴爬蟲 ===\n")
    results = {}
    studios = {}  # name -> maker_id

    # 補齊 maker ID
    print("-- 查詢片商 maker ID --")
    for studio_name, (maker_id, sample_code) in STUDIOS_LOOKUP.items():
        if maker_id:
            studios[studio_name] = maker_id
            print(f"  {studio_name}: ID = {maker_id} (已知)")
        else:
            print(f"  {studio_name}: 透過 {sample_code} 查詢...")
            found_id = find_maker_id_via_video(sample_code)
            if found_id:
                studios[studio_name] = found_id
                print(f"  {studio_name}: 找到 ID = {found_id}")
            else:
                studios[studio_name] = None
                print(f"  {studio_name}: 找不到 ID，跳過")
            time.sleep(1.5)
    print()

    for studio_name, maker_id in studios.items():
        if not maker_id:
            results[studio_name] = []
            continue
        codes = fetch_studio(studio_name, maker_id)
        results[studio_name] = codes
        time.sleep(2)

    output_path = "tools/javdb_studio_codes.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n結果已寫入 {output_path}")
    print("\n=== 完整結果 ===")
    for studio, codes in results.items():
        print(f"{studio:15s}: {codes}")


if __name__ == "__main__":
    main()
