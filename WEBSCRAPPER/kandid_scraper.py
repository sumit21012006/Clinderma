import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

# Configure UTF-8 encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Allow importing from backend/app/services if running from workspace root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
try:
    from app.services.kandid_service import KandidWebSocketClient, KandidResponse
except ImportError:
    # If standalone in WEBSCRAPPER directory
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    from kandid_service import KandidWebSocketClient, KandidResponse


OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "output"))


def print_colored(text: str, color_code: str = "36", end: str = "\n", flush: bool = True):
    print(f"\033[{color_code}m{text}\033[0m", end=end, flush=flush)


async def run_single_query(
    client: KandidWebSocketClient,
    query: str,
    output_dir: str = OUTPUT_DIR,
    session_id: str = None
) -> KandidResponse:
    print_colored(f"\n==================================================", "34")
    print_colored(f"[QUERY]: {query}", "1;37")
    print_colored(f"==================================================", "34")
    print_colored("[Kandid AI Streaming Response]:\n", "33")

    def on_chunk(text: str):
        print(text, end="", flush=True)

    response = await client.query(query=query, session_id=session_id, on_text_chunk=on_chunk)

    print("\n")
    print_colored(f"[INFO] Duration: {response.duration_seconds}s | Received {response.events_count} frames", "90")

    if response.products:
        print_colored("\n[RECOMMENDED PRODUCTS]:", "1;32")
        for idx, prod in enumerate(response.products, 1):
            price_tag = f" [Rs. {prod.price}]" if prod.price else ""
            print_colored(f"  {idx}. {prod.title}{price_tag}", "32")
            if prod.url:
                print_colored(f"     URL: {prod.url}", "90")
            if prod.body_markdown:
                print_colored(f"     Info: {prod.body_markdown}", "37")

    if response.follow_ups:
        print_colored("\n[SUGGESTED FOLLOW-UPS]:", "1;35")
        for f in response.follow_ups:
            print_colored(f"  Question: {f.question}", "35")
            for opt in f.options:
                print_colored(f"   - {opt}", "37")

    # Save to disk
    os.makedirs(output_dir, exist_ok=True)
    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_query_slug = "".join([c if c.isalnum() else "_" for c in query])[:30].strip("_")
    filename_base = f"{timestamp_slug}_{clean_query_slug}"

    json_path = os.path.join(output_dir, f"{filename_base}.json")
    md_path = os.path.join(output_dir, f"{filename_base}.md")
    jsonl_path = os.path.join(output_dir, "all_responses.jsonl")

    response.save_json(json_path)
    response.save_markdown(md_path)
    response.append_to_jsonl(jsonl_path)

    print_colored(f"\n[SAVED]:", "90")
    print_colored(f"   - JSON:     {json_path}", "90")
    print_colored(f"   - Markdown: {md_path}", "90")
    print_colored(f"   - Dataset:  {jsonl_path}", "90")

    return response


async def interactive_mode(client: KandidWebSocketClient, output_dir: str = OUTPUT_DIR):
    print_colored("\n========================================================", "1;36")
    print_colored("     Kandid AI WebSocket Interactive Scraper & Parser   ", "1;36")
    print_colored("========================================================", "1;36")
    print_colored("Type your query and press Enter. Type 'exit' or 'quit' to quit.\n", "37")

    session_id = f"session_{int(datetime.now().timestamp())}"

    while True:
        try:
            query = input("\033[1;32mYour Query > \033[0m").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                print_colored("Goodbye!", "33")
                break
            await run_single_query(client, query=query, output_dir=output_dir, session_id=session_id)
            print("\n" + "-" * 50 + "\n")
        except (KeyboardInterrupt, EOFError):
            print_colored("\nExiting...", "33")
            break


async def batch_mode(
    client: KandidWebSocketClient,
    input_file: str,
    output_dir: str = OUTPUT_DIR,
    delay: float = 2.0
):
    if not os.path.exists(input_file):
        print_colored(f"[ERROR] Input file not found: {input_file}", "31")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        queries = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    print_colored(f"[BATCH] Loaded {len(queries)} queries for scraping.", "36")
    for i, q in enumerate(queries, 1):
        print_colored(f"\n--- Processing [{i}/{len(queries)}] ---", "34")
        try:
            await run_single_query(client, query=q, output_dir=output_dir)
        except Exception as e:
            print_colored(f"[ERROR] Error processing query '{q}': {e}", "31")
        if i < len(queries):
            await asyncio.sleep(delay)

    print_colored(f"\n[DONE] Batch processing complete! Results saved in: {output_dir}", "1;32")


def main():
    parser = argparse.ArgumentParser(description="Kandid AI WebSocket Client & Response Parser")
    parser.add_argument("--query", "-q", type=str, help="Single query to send")
    parser.add_argument("--batch", "-b", type=str, help="File containing queries (one per line)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive chat mode")
    parser.add_argument("--output", "-o", type=str, default=OUTPUT_DIR, help="Output directory to save responses")
    parser.add_argument("--url", type=str, default="wss://communicate.kandid.ai/socket/?EIO=4&transport=websocket", help="WebSocket URL")
    parser.add_argument("--agent-id", type=str, default="nz5MJ59H80ZlsN-Y2cb8I", help="Kandid Agent ID")
    parser.add_argument("--avatar-id", type=str, default="xr7arYZWBbbp26V8ZVoX4", help="Kandid Avatar ID")

    args = parser.parse_args()

    client = KandidWebSocketClient(
        ws_url=args.url,
        agent_id=args.agent_id,
        avatar_id=args.avatar_id
    )

    if args.query:
        asyncio.run(run_single_query(client, query=args.query, output_dir=args.output))
    elif args.batch:
        asyncio.run(batch_mode(client, input_file=args.batch, output_dir=args.output))
    else:
        asyncio.run(interactive_mode(client, output_dir=args.output))


if __name__ == "__main__":
    main()
