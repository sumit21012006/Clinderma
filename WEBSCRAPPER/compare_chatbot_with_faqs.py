import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# Windows UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from app.services.kandid_service import KandidWebSocketClient, KandidResponse

DEFAULT_FAQS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "master_faqs.json"))
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "comparison_results"))


def print_c(text: str, code: str = "36", end: str = "\n", flush: bool = True):
    print(f"\033[{code}m{text}\033[0m", end=end, flush=flush)


def calculate_keyword_coverage(chatbot_text: str, keywords: List[str]) -> Dict[str, Any]:
    text_lower = chatbot_text.lower()
    matched = []
    missing = []
    for kw in keywords:
        # Check if individual words or phrase appears
        kw_lower = kw.lower()
        if kw_lower in text_lower or any(word in text_lower for word in kw_lower.split() if len(word) > 4):
            matched.append(kw)
        else:
            missing.append(kw)
    
    score = round((len(matched) / len(keywords)) * 100, 1) if keywords else 100.0
    return {
        "matched_keywords": matched,
        "missing_keywords": missing,
        "coverage_percent": score
    }


def calculate_key_point_coverage(chatbot_text: str, key_points: List[str]) -> Dict[str, Any]:
    text_lower = chatbot_text.lower()
    covered = []
    not_covered = []

    for kp in key_points:
        # Simple extraction of significant words (>4 chars) in the key point
        words = [w.lower().strip(".,()[]{}") for w in kp.split() if len(w) > 4]
        match_count = sum(1 for w in words if w in text_lower)
        if words and (match_count / len(words)) >= 0.35:
            covered.append(kp)
        else:
            not_covered.append(kp)

    score = round((len(covered) / len(key_points)) * 100, 1) if key_points else 100.0
    return {
        "covered_key_points": covered,
        "uncovered_key_points": not_covered,
        "score_percent": score
    }


async def evaluate_single_faq(
    client: KandidWebSocketClient,
    faq: Dict[str, Any],
    stream: bool = True
) -> Dict[str, Any]:
    faq_id = faq.get("id")
    question = faq.get("question")
    ground_truth = faq.get("answer")
    keywords = faq.get("keywords", [])
    key_points = faq.get("key_points", [])

    print_c(f"\n=======================================================", "34")
    print_c(f"[{faq_id}] {question}", "1;37")
    print_c(f"Category: {faq.get('category')} | Cohort: {faq.get('cohort')}", "90")
    print_c("=======================================================", "34")
    print_c("🤖 Live Kandid AI Chatbot Response:\n", "33")

    def on_chunk(c: str):
        if stream:
            print(c, end="", flush=True)

    response: KandidResponse = await client.query(query=question, on_text_chunk=on_chunk)
    if stream:
        print("\n")

    kw_eval = calculate_keyword_coverage(response.full_text, keywords)
    kp_eval = calculate_key_point_coverage(response.full_text, key_points)

    result = {
        "id": faq_id,
        "category": faq.get("category"),
        "cohort": faq.get("cohort"),
        "question": question,
        "ground_truth_answer": ground_truth,
        "chatbot_response": response.full_text,
        "duration_seconds": response.duration_seconds,
        "products_recommended": [p.model_dump() for p in response.products],
        "follow_ups": [f.model_dump() for f in response.follow_ups],
        "keyword_coverage": kw_eval,
        "key_point_coverage": kp_eval,
        "alignment_score": round((kw_eval["coverage_percent"] * 0.4) + (kp_eval["score_percent"] * 0.6), 1)
    }

    print_c(f"📊 Alignment Score: {result['alignment_score']}% (Keywords: {kw_eval['coverage_percent']}%, Key Points: {kp_eval['score_percent']}%)", "1;32" if result['alignment_score'] >= 70 else "1;33")
    if response.products:
        print_c(f"🛍️  Products returned: {len(response.products)} ({', '.join([p.title for p in response.products])})", "32")

    return result


def generate_comparison_markdown(results: List[Dict[str, Any]]) -> str:
    avg_score = round(sum(r["alignment_score"] for r in results) / len(results), 1) if results else 0
    lines = [
        "# Clinderma Master FAQs vs. Live Kandid AI Chatbot Evaluation Report",
        f"**Date**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"**Evaluated Questions**: `{len(results)}` | **Average Alignment Score**: `{avg_score}%`",
        "",
        "## 📈 Summary Table",
        "| ID | Question | Category | Alignment Score | Products | Duration |",
        "|---|---|---|---|---|---|"
    ]

    for r in results:
        status_emoji = "✅" if r["alignment_score"] >= 70 else ("⚠️" if r["alignment_score"] >= 50 else "❌")
        q_snippet = r["question"][:45] + ("..." if len(r["question"]) > 45 else "")
        prod_count = len(r["products_recommended"])
        lines.append(f"| {r['id']} | {q_snippet} | {r['category']} | {status_emoji} {r['alignment_score']}% | {prod_count} prods | {r['duration_seconds']}s |")

    lines.append("\n---\n")
    lines.append("## 🔍 Detailed Question-by-Question Comparison\n")

    for idx, r in enumerate(results, 1):
        lines.append(f"### {idx}. [{r['id']}] {r['question']}")
        lines.append(f"- **Category**: `{r['category']}` | **Cohort**: `{r['cohort']}`")
        lines.append(f"- **Alignment Score**: `{r['alignment_score']}%`")
        lines.append("")
        lines.append("#### 📖 Ground-Truth Master Answer:")
        lines.append(f"> {r['ground_truth_answer'].replace(chr(10), chr(10) + '> ')}")
        lines.append("")
        lines.append("#### 🤖 Live Chatbot Response:")
        lines.append(f"{r['chatbot_response']}")
        lines.append("")

        if r["products_recommended"]:
            lines.append("#### 🛍️ Recommended Products:")
            for p in r["products_recommended"]:
                price = f" - ₹{p.get('price')}" if p.get('price') else ""
                lines.append(f"- **{p.get('title')}**{price} ([Link]({p.get('url')}))")
            lines.append("")

        if r["follow_ups"]:
            lines.append("#### ❓ Suggested Follow-ups:")
            for f in r["follow_ups"]:
                lines.append(f"- **{f.get('question')}**: {', '.join(f.get('options', []))}")
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)


async def main_async(args):
    faqs_path = args.faqs or DEFAULT_FAQS_PATH
    if not os.path.exists(faqs_path):
        print_c(f"❌ FAQs file not found: {faqs_path}", "31")
        return

    with open(faqs_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    faqs = data.get("faqs", [])
    print_c(f"Loaded {len(faqs)} Master FAQs from {faqs_path}", "36")

    # Filter if arguments provided
    if args.id:
        faqs = [f for f in faqs if f.get("id", "").lower() == args.id.lower()]
    elif args.category:
        faqs = [f for f in faqs if args.category.lower() in f.get("category", "").lower()]
    elif args.cohort:
        target_cohort = args.cohort.strip().lower()
        faqs = [f for f in faqs if f.get("cohort", "").strip().lower() == target_cohort or target_cohort in [c.strip().lower() for c in f.get("cohort", "").split("/")]]

    if args.limit:
        faqs = faqs[:args.limit]

    print_c(f"Testing {len(faqs)} FAQs against live Kandid AI WebSocket...", "36")

    client = KandidWebSocketClient(ws_url=args.url)
    results = []

    for i, faq in enumerate(faqs, 1):
        print_c(f"\n[{i}/{len(faqs)}] Processing {faq.get('id')}...", "35")
        try:
            res = await evaluate_single_faq(client, faq, stream=not args.quiet)
            results.append(res)
        except Exception as e:
            print_c(f"❌ Error evaluating {faq.get('id')}: {e}", "31")

        if i < len(faqs):
            await asyncio.sleep(args.delay)

    # Save results
    os.makedirs(args.output, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_json_path = os.path.join(args.output, f"faq_comparison_{timestamp}.json")
    report_md_path = os.path.join(args.output, f"faq_comparison_{timestamp}.md")
    latest_json = os.path.join(args.output, "latest_comparison.json")
    latest_md = os.path.join(args.output, "latest_comparison.md")

    report_data = {
        "metadata": {
            "timestamp": timestamp,
            "total_evaluated": len(results),
            "faqs_source": faqs_path,
            "average_alignment_score": round(sum(r["alignment_score"] for r in results) / len(results), 1) if results else 0
        },
        "results": results
    }

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    with open(latest_json, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    md_content = generate_comparison_markdown(results)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    with open(latest_md, "w", encoding="utf-8") as f:
        f.write(md_content)

    print_c(f"\n=======================================================", "1;32")
    print_c(f"✅ Evaluation Complete! Reports Generated:", "1;32")
    print_c(f"   - JSON Report: {report_json_path}", "37")
    print_c(f"   - Markdown:    {report_md_path}", "37")
    print_c(f"=======================================================\n", "1;32")


def main():
    parser = argparse.ArgumentParser(description="Compare Clinderma Master FAQs against Live Kandid AI WebSocket")
    parser.add_argument("--id", type=str, help="Evaluate a specific FAQ ID (e.g. faq_01, faq_04)")
    parser.add_argument("--category", type=str, help="Filter FAQs by category name")
    parser.add_argument("--cohort", type=str, help="Filter FAQs by cohort (Teens, Women, Men, General)")
    parser.add_argument("--limit", "-l", type=int, help="Limit number of FAQs to evaluate")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between requests")
    parser.add_argument("--faqs", type=str, default=DEFAULT_FAQS_PATH, help="Path to master_faqs.json")
    parser.add_argument("--output", "-o", type=str, default=OUTPUT_DIR, help="Output directory for reports")
    parser.add_argument("--url", type=str, default="wss://communicate.kandid.ai/socket/?EIO=4&transport=websocket", help="WebSocket URL")
    parser.add_argument("--quiet", action="store_true", help="Do not stream response tokens live")

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
