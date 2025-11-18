import httpx
from bs4 import BeautifulSoup

print("正在訪問 MIDA-101...")
r = httpx.get('https://av-wiki.net/product/mida-101/', timeout=30, follow_redirects=True)
print(f"狀態碼: {r.status_code}")
print(f"內容長度: {len(r.text)} 字元\n")

soup = BeautifulSoup(r.text, 'html.parser')

# 檢查所有連結
all_links = soup.find_all('a')
print(f"總共找到 {len(all_links)} 個連結\n")

# 查找女優連結
actress_links = []
for a in all_links:
    href = a.get('href', '')
    text = a.get_text(strip=True)
    if 'tag/actress' in href or '/actress/' in href or 'タグ/女優' in href:
        actress_links.append((href, text))

print(f"女優連結 ({len(actress_links)}):")
for href, text in actress_links[:15]:
    print(f"  - {text}")
    print(f"    {href}")

# 查找所有 rel="tag" 的連結
print("\n\n所有 rel='tag' 連結:")
tag_links = soup.find_all('a', rel='tag')
print(f"找到 {len(tag_links)} 個")
for t in tag_links[:20]:
    print(f"  - {t.get_text(strip=True)} | {t.get('href', '')}")

