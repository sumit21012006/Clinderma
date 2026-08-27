import re
import json
import time
import requests
import html as html_lib
from lxml import html
from typing import Dict, List, Optional
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
}


def clean_spaces(text: str) -> str:
    if not text:
        return ""
    text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\u2028', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def element_to_markdown(el) -> str:
    tag = el.tag.lower() if isinstance(el.tag, str) else ""

    if tag in ("script", "style", "noscript", "svg", "button"):
        return ""

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = tag[1]
        text = "".join(el.xpath(".//text()")).strip()
        text = clean_spaces(text)
        return f"{'#' * int(level)} {text}\n\n" if text else ""

    if tag == "p":
        inner_md = ""
        for child in el.iterchildren():
            child_tag = child.tag.lower() if isinstance(child.tag, str) else ""
            child_text = "".join(child.xpath(".//text()")).strip()
            child_text = clean_spaces(child_text)
            if not child_text:
                continue

            if child_tag in ("strong", "b"):
                inner_md += f" **{child_text}** "
            elif child_tag in ("em", "i"):
                inner_md += f" *{child_text}* "
            elif child_tag == "a":
                href = child.get("href", "")
                inner_md += f" [{child_text}]({href}) " if href else f" {child_text} "
            elif child_tag == "span":
                if child.xpath(".//strong | .//b"):
                    inner_md += f" **{child_text}** "
                else:
                    inner_md += f" {child_text} "
            else:
                inner_md += f" {child_text} "

        if not inner_md.strip():
            raw_text = "".join(el.xpath(".//text()")).strip()
            raw_text = clean_spaces(raw_text)
            if el.xpath(".//strong | .//b") and len(el.xpath(".//text()")) <= 2:
                inner_md = f"**{raw_text}**"
            else:
                inner_md = raw_text

        inner_md = clean_spaces(inner_md)
        return f"{inner_md}\n\n" if inner_md else ""

    if tag in ("ul", "ol"):
        items = []
        is_ol = (tag == "ol")
        for i, li in enumerate(el.xpath("./li"), 1):
            li_text = "".join(li.xpath(".//text()")).strip()
            li_text = clean_spaces(li_text)
            if li_text:
                prefix = f"{i}. " if is_ol else "- "
                items.append(f"{prefix}{li_text}")
        return "\n".join(items) + "\n\n" if items else ""

    if tag == "li":
        text = "".join(el.xpath(".//text()")).strip()
        text = clean_spaces(text)
        return f"- {text}\n" if text else ""

    if tag == "blockquote":
        text = "".join(el.xpath(".//text()")).strip()
        text = clean_spaces(text)
        return f"> {text}\n\n" if text else ""

    if tag == "table":
        rows = []
        for tr in el.xpath(".//tr"):
            cells = [clean_spaces("".join(c.xpath(".//text()"))) for c in tr.xpath("./th | ./td")]
            if any(cells):
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            cols_count = len(el.xpath(".//tr[1]/th | .//tr[1]/td"))
            sep = "| " + " | ".join(["---"] * cols_count) + " |"
            if len(rows) > 1:
                rows.insert(1, sep)
            return "\n".join(rows) + "\n\n"

    texts = []
    for child in el:
        child_md = element_to_markdown(child)
        if child_md:
            texts.append(child_md)

    if not texts:
        direct = "".join(el.xpath(".//text()")).strip()
        direct = clean_spaces(direct)
        return f"{direct}\n\n" if direct else ""

    return "".join(texts)


def extract_single_article(url: str) -> Dict[str, str]:
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        raise ValueError(f"HTTP {r.status_code} fetching {url}")

    tree = html.fromstring(r.content)

    # 1. Title
    title = ""
    h1_elements = tree.xpath("//h1")
    if h1_elements:
        title = clean_spaces("".join(h1_elements[0].xpath(".//text()")))

    if not title:
        title_tags = tree.xpath("//title/text()")
        if title_tags:
            title = clean_spaces(title_tags[0])
            title = re.sub(r'\s*[—\-\|]\s*Clinderma.*$', '', title, flags=re.IGNORECASE)

    # 2. Body from div.blog-content
    content_blocks = []
    blog_content_divs = tree.xpath("//div[contains(@class, 'blog-content')]")

    if blog_content_divs:
        container = blog_content_divs[0]
        for child in container:
            child_tag = child.tag.lower() if isinstance(child.tag, str) else ""
            if child_tag in ("script", "style", "noscript"):
                continue
            md = element_to_markdown(child)
            if md and md.strip():
                content_blocks.append(md.strip())

    # Fallback to RSC if empty DOM
    if not content_blocks:
        scripts = tree.xpath("//script/text()")
        rsc_blocks = []
        for s in scripts:
            if "__next_f" in s:
                matches = re.findall(r'self\.__next_f\.push\(\[\d+,\s*"(.*?)"\]\)', s, re.DOTALL)
                for m in matches:
                    try:
                        decoded = bytes(m, "utf-8").decode("unicode_escape")
                        rsc_blocks.append(decoded)
                    except Exception:
                        rsc_blocks.append(m)

        combined_rsc = "\n".join(rsc_blocks)
        p_matches = re.findall(r'<(p|ul|ol|h2|h3|blockquote)[^>]*>.*?</\1>', combined_rsc, re.DOTALL)
        for pm in p_matches:
            try:
                fragment = html.fromstring(pm)
                md = element_to_markdown(fragment)
                if md and md.strip():
                    content_blocks.append(md.strip())
            except Exception:
                pass

    full_content = "\n\n".join(content_blocks).strip()
    full_content = html_lib.unescape(full_content)
    title = html_lib.unescape(title)

    return {
        "title": title,
        "content": full_content
    }


def discover_all_blog_metadata() -> List[Dict[str, str]]:
    url = "https://www.theclinderma.com/blog"
    r = requests.get(url, headers=HEADERS, timeout=15)
    
    matches = re.findall(r'self\.__next_f\.push\(\[\d+,\s*"(.*?)"\]\)', r.text, re.DOTALL)
    decoded_text = ""
    for m in matches:
        try:
            decoded_text += bytes(m, "utf-8").decode("unicode_escape")
        except Exception:
            decoded_text += m

    slug_positions = [m.start() for m in re.finditer(r'"slug"\s*:\s*"[^"]+"', decoded_text)]
    extracted = []
    seen = set()

    for p in slug_positions:
        chunk = decoded_text[max(0, p-100):min(len(decoded_text), p+300)]
        slug_m = re.search(r'"slug"\s*:\s*"([^"]+)"', chunk)
        title_m = re.search(r'"title"\s*:\s*"([^"]+)"', chunk)
        cat_m = re.search(r'"category"\s*:\s*"([^"]+)"', chunk)

        if slug_m:
            slug = slug_m.group(1)
            if not slug.startswith("layout") and not slug.startswith("page") and slug != "la" and slug not in seen:
                seen.add(slug)
                extracted.append({
                    "slug": slug,
                    "url": f"https://www.theclinderma.com/blog/{slug}",
                    "title_meta": title_m.group(1) if title_m else None,
                    "category": cat_m.group(1) if cat_m else "General"
                })

    return extracted


def scrape_all_blogs(output_path: str = "WEBSCRAPPER/clinderma_all_blogs.json"):
    blogs_meta = discover_all_blog_metadata()
    print(f"🚀 Starting extraction of all {len(blogs_meta)} blog articles...\n")

    final_dataset = []
    errors = []

    for i, b in enumerate(blogs_meta, 1):
        url = b["url"]
        print(f"[{i:02d}/{len(blogs_meta)}] Fetching: {b['slug']} ({b.get('category')})")
        try:
            art = extract_single_article(url)
            # Match strictly requested format: [{"title": "...", "content": "..."}]
            final_dataset.append({
                "title": art["title"] or b.get("title_meta", ""),
                "content": art["content"]
            })
            print(f"       ✅ '{art['title'][:45]}...' ({len(art['content'])} chars)")
        except Exception as e:
            print(f"       ❌ Failed: {e}")
            errors.append({"url": url, "error": str(e)})

        time.sleep(0.5)

    # Save final dataset
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_dataset, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 Completed! Successfully extracted {len(final_dataset)}/{len(blogs_meta)} articles.")
    print(f"💾 Saved complete dataset to: {output_path}")

    if errors:
        err_path = output_path.replace(".json", "_errors.json")
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        print(f"⚠️ Recorded {len(errors)} errors in: {err_path}")

    return final_dataset


if __name__ == "__main__":
    scrape_all_blogs()
