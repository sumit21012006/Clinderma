# Kandid AI WebSocket Client, Scraper & Parser

A complete client and structured parser for communicating with the Kandid AI WebSocket protocol (`wss://communicate.kandid.ai/socket/?EIO=4&transport=websocket`).

---

## 🔍 Why Postman Was "Vague"

Kandid AI uses **Engine.IO v4 + Socket.IO v4** raw framing over WebSockets:
1. **Handshake Requirement**: When you connect, the server sends `0{"sid":"..."}`. You **must immediately reply** with `40` (Socket.IO default namespace connection). If you send queries directly without `40`, the server terminates the socket immediately (`1005` error).
2. **Ping / Pong Heartbeats**: The server sends `2` periodically. The client must reply with `3` (pong).
3. **Response Streaming & Frame Fragmentation**:
   - In Postman, responses arrive as dozens of separate, unstitched packets like `42["assistant-response",{"content":"Acne ca"}]`, `42["assistant-response",{"content":"n improve"}]`.
   - Postman does not concatenate tokens, does not parse JSON payloads, and does not aggregate product cards or follow-up questions.
4. **Structured Event Payloads**: The server broadcasts multiple event types on `42[...]`:
   - `thinkingStateFromServer`: Progress indicator (`THINKING`)
   - `assistant-response`: Streaming markdown token chunks
   - `product-recommendations`: Array of rich product catalog objects (ID, title, price in INR, handle, Shopify images, variants, suggested follow-up queries)
   - `follow-up-question`: Suggested prompt options for the user

---

## 🚀 Features

- **Automated Handshake & Heartbeat**: Handles Engine.IO `0` -> `40` handshake and `2` -> `3` keepalive automatically.
- **Stream Reassembly**: Concatenates token chunks into complete Markdown text in real time.
- **Rich Product Extraction**: Extracts product titles, prices (INR), direct shop URLs (`https://www.theclinderma.com/products/...`), descriptions, and CDN image URLs.
- **Interactive CLI & Batch Scraping**: Run single queries, interactive chat, or batch scrape from query lists.
- **Multi-Format Storage**:
  - `JSON`: Full structured object with metadata, products, and raw frame logs.
  - `Markdown`: Formatted, readable report with embedded images and product links.
  - `JSONL`: Appends to `all_responses.jsonl` for training, RAG, or dataset generation.

---

## 💻 CLI Usage

### 1. Interactive Mode (Chat in Terminal)
```bash
python WEBSCRAPPER/kandid_scraper.py
```

### 2. Single Query
```bash
python WEBSCRAPPER/kandid_scraper.py --query "What is the best routine for dark spots and hyperpigmentation?"
```

### 3. Batch Scraping from File
```bash
python WEBSCRAPPER/kandid_scraper.py --batch WEBSCRAPPER/sample_queries.txt --output WEBSCRAPPER/output/
```

---

## 🐍 Programmatic Python Usage

```python
import asyncio
from backend.app.services.kandid_service import KandidWebSocketClient

async def main():
    client = KandidWebSocketClient()
    
    # 1. Real-time streaming
    def on_chunk(chunk: str):
        print(chunk, end="", flush=True)

    response = await client.query(
        query="Recommend products for cystic acne",
        on_text_chunk=on_chunk
    )
    
    print("\n--- Parsed Summary ---")
    print("Full Text:", response.full_text)
    print("Products Found:", len(response.products))
    for p in response.products:
        print(f"- {p.title} (₹{p.price}): {p.url}")
    
    # Save files
    response.save_json("cystic_acne.json")
    response.save_markdown("cystic_acne.md")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📦 Output Formats

### JSON Output Sample:
```json
{
  "session_id": "QphAdfZ6lm-yzk2mrTF8U",
  "query": "What is the best routine for dark spots?",
  "full_text": "For dark spots and hyperpigmentation, consistency and sunscreen matter the most...",
  "products": [
    {
      "id": 65390,
      "title": "Melalumin Face Wash",
      "handle": "melalumin-face-wash",
      "price": "425.00",
      "url": "https://www.theclinderma.com/products/melalumin-face-wash",
      "body_markdown": "A depigmenting face wash with glycolic acid and niacinamide...",
      "images": [{"src": "https://cdn.shopify.com/s/files/1/0916/8178/4120/files/Melaluminfacewashfront.png"}]
    }
  ],
  "follow_ups": [
    {
      "question": "What kind of pigmentation are you dealing with?",
      "options": ["I have post-acne dark spots", "I have uneven skin tone"]
    }
  ],
  "duration_seconds": 3.82,
  "events_count": 84
}
```
