import re
import json
import html as html_lib
import requests
from lxml import html, etree
from typing import Dict, List, Optional, Tuple
import sys

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
    """Normalize non-breaking spaces and redundant horizontal whitespace."""
    if not text:
        return ""
    text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\u2028', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def element_to_markdown(el) -> str:
    """
    Recursively converts an HTML element into clean readable text/Markdown.
    Preserves strong/bold, italics, headings, lists, tables, links, and paragraphs.
    """
    tag = el.tag.lower() if isinstance(el.tag, str) else ""

    if tag in ("script", "style", "noscript", "svg", "button"):
        return ""

    # Check if element itself is a header or list
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = tag[1]
        text = "".join(el.xpath(".//text()")).strip()
        text = clean_spaces(text)
        return f"{'#' * int(level)} {text}\n\n" if text else ""

    if tag == "p":
        # Check if the paragraph is entirely bold / a section title like <p><strong>...</strong></p>
        # or has mixed content
        inner_md = ""
        # Process child nodes preserving inline tags
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
                # Check if inside span there is strong
                if child.xpath(".//strong | .//b"):
                    inner_md += f" **{child_text}** "
                else:
                    inner_md += f" {child_text} "
            else:
                inner_md += f" {child_text} "

        # If iterchildren didn't catch direct text
        if not inner_md.strip():
            raw_text = "".join(el.xpath(".//text()")).strip()
            raw_text = clean_spaces(raw_text)
            # Check if this element had strong/b
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
            # Insert header separator after first row
            cols_count = len(el.xpath(".//tr[1]/th | .//tr[1]/td"))
            sep = "| " + " | ".join(["---"] * cols_count) + " |"
            if len(rows) > 1:
                rows.insert(1, sep)
            return "\n".join(rows) + "\n\n"

    # Default fallback: extract text of children
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


def extract_blog_article(url: str, html_text: Optional[str] = None) -> Dict[str, str]:
    """
    Fetches and extracts article title and complete content from a blog URL.
    Returns: {"title": "...", "content": "..."}
    """
    if not html_text:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code} fetching {url}")
        html_text = r.text

    tree = html.fromstring(html_text)

    # 1. Extract Title
    title = ""
    h1_elements = tree.xpath("//h1")
    if h1_elements:
        title = clean_spaces("".join(h1_elements[0].xpath(".//text()")))

    if not title:
        # Fallback to <title> tag (stripping site suffix)
        title_tags = tree.xpath("//title/text()")
        if title_tags:
            title = clean_spaces(title_tags[0])
            title = re.sub(r'\s*[—\-\|]\s*Clinderma.*$', '', title, flags=re.IGNORECASE)

    # 2. Extract Article Content from DOM
    # The primary container is div.blog-content
    content_blocks = []
    blog_content_divs = tree.xpath("//div[contains(@class, 'blog-content')]")

    if blog_content_divs:
        container = blog_content_divs[0]
        # Iterate over all top-level child elements of the blog-content container
        for child in container:
            # Skip any scripts/styles or recommendations
            child_tag = child.tag.lower() if isinstance(child.tag, str) else ""
            if child_tag in ("script", "style", "noscript"):
                continue

            md = element_to_markdown(child)
            if md and md.strip():
                content_blocks.append(md.strip())

    # Fallback to Next.js RSC payload if DOM container was empty
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
        # Extract <p> and <ul> tags from RSC
        p_matches = re.findall(r'<(p|ul|ol|h2|h3|blockquote)[^>]*>.*?</\1>', combined_rsc, re.DOTALL)
        for pm in p_matches:
            try:
                fragment = html.fromstring(pm)
                md = element_to_markdown(fragment)
                if md and md.strip():
                    content_blocks.append(md.strip())
            except Exception:
                pass

    # Clean and assemble full content
    full_content = "\n\n".join(content_blocks).strip()

    # Final cleanup of double spaces or HTML entities
    full_content = html_lib.unescape(full_content)
    title = html_lib.unescape(title)

    return {
        "title": title,
        "content": full_content
    }


def test_extraction_on_3_articles():
    test_urls = [
        "https://www.theclinderma.com/blog/pimples-during-pregnancy-causes-amp-safe-treatments-nbsp",
        "https://www.theclinderma.com/blog/why-am-i-getting-tiny-bumps-on-my-forehead",
        "https://www.theclinderma.com/blog/do-you-need-a-moisturizer-if-you-have-pimples"
    ]

    results = []
    print(f"Testing extraction on {len(test_urls)} sample articles...\n")

    for i, url in enumerate(test_urls, 1):
        print(f"[{i}/{len(test_urls)}] Fetching & parsing: {url}")
        try:
            art = extract_blog_article(url)
            results.append({
                "url": url,
                "title": art["title"],
                "content_preview": art["content"][:300] + "...",
                "content_length": len(art["content"]),
                "full_data": art
            })
            print(f"  Title: {art['title']}")
            print(f"  Content length: {len(art['content'])} chars")
            print(f"  Paragraphs count: {len(art['content'].split(chr(10)+chr(10)))}\n")
        except Exception as e:
            print(f"  Error: {e}\n")

    # Save test output
    with open("e:/Projects/Clinderma/WEBSCRAPPER/test_3_articles.json", "w", encoding="utf-8") as f:
        json.dump([r["full_data"] for r in results], f, indent=2, ensure_ascii=False)

    print("Saved test results to WEBSCRAPPER/test_3_articles.json")
    return results


if __name__ == "__main__":
    test_extraction_on_3_articles()
