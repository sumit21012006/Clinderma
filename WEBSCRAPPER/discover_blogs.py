import re
import json
import requests
from lxml import html
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def discover_all_blog_links():
    url = "https://www.theclinderma.com/blog"
    print(f"Fetching {url}...")
    r = requests.get(url, headers=headers, timeout=15)
    print(f"Status: {r.status_code}, Length: {len(r.text)} bytes")

    # 1. Direct HTML links
    tree = html.fromstring(r.content)
    raw_hrefs = tree.xpath("//a/@href")
    
    found_urls = set()
    for h in raw_hrefs:
        if "/blog/" in h:
            if h.startswith("http"):
                found_urls.add(h)
            elif h.startswith("/"):
                found_urls.add("https://www.theclinderma.com" + h)

    print(f"Found {len(found_urls)} blog links in HTML anchor tags.")

    # 2. Extract from RSC script tags
    # Find all script contents
    scripts = tree.xpath("//script/text()")
    rsc_payloads = []
    for s in scripts:
        if "__next_f" in s:
            # Extract JSON-like string arguments inside self.__next_f.push([1, "..."])
            # or self.__next_f.push([1, "some string"])
            matches = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', s, re.DOTALL)
            for m in matches:
                try:
                    # Clean escaped quotes/backslashes
                    decoded = bytes(m, "utf-8").decode("unicode_escape")
                    rsc_payloads.append(decoded)
                except Exception:
                    rsc_payloads.append(m)

    combined_rsc = "\n".join(rsc_payloads)
    print(f"Combined RSC text length: {len(combined_rsc)} chars")

    # Look for slugs or blog objects in RSC payload
    # Patterns like "slug":"pimples-during-pregnancy-causes-amp-safe-treatments-nbsp"
    # or "/blog/pimples-during-pregnancy..."
    rsc_slugs = set(re.findall(r'/blog/([a-zA-Z0-9_\-\&\%]+)', combined_rsc))
    print(f"Found {len(rsc_slugs)} unique blog slugs in RSC payload:")
    for s in sorted(rsc_slugs):
        full_url = f"https://www.theclinderma.com/blog/{s}"
        found_urls.add(full_url)
        print(f"  - {full_url}")

    # Check for any API or data endpoints or JSON objects in RSC
    # Let's see if there are JSON objects with title, slug, id, category, etc.
    json_blog_objects = re.findall(r'\{[^{}]*?"slug"\s*:\s*"([^"]+)"[^{}]*?\}', combined_rsc)
    print(f"Blog objects with 'slug': {len(json_blog_objects)}")
    for sl in json_blog_objects:
        full_url = f"https://www.theclinderma.com/blog/{sl}"
        found_urls.add(full_url)

    print(f"\nTotal unique blog URLs discovered: {len(found_urls)}")
    for u in sorted(found_urls):
        print(f"  * {u}")

    return sorted(found_urls)

if __name__ == "__main__":
    discover_all_blog_links()
