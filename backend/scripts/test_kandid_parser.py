import asyncio
import json
import websockets

WS_URL = "wss://communicate.kandid.ai/socket/?EIO=4&transport=websocket"

async def query_kandid(prompt: str, session_id: str = "QphAdfZ6lm-yzk2mrTF8U"):
    headers = {
        "Origin": "https://communicate.kandid.ai",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    payload = {
        "sessionId": session_id,
        "agentId": "nz5MJ59H80ZlsN-Y2cb8I",
        "avatarId": "xr7arYZWBbbp26V8ZVoX4",
        "id": 1,
        "kandidShopifyStore": None,
        "path": "/en",
        "query": {
            "type": "TEXT",
            "query": prompt
        }
    }

    print(f"Connecting to {WS_URL}...", flush=True)
    async with websockets.connect(WS_URL, additional_headers=headers) as ws:
        # Handshake
        handshake = await ws.recv()
        # Connect socket.io
        await ws.send("40")
        ack = await ws.recv()

        # Send query
        msg = f'42["user-query",{json.dumps(payload)}]'
        await ws.send(msg)

        full_text = []
        products = []
        follow_ups = []
        thinking_states = []
        raw_events = []

        try:
            while True:
                frame = await asyncio.wait_for(ws.recv(), timeout=12.0)
                if frame == "2":
                    await ws.send("3")
                    continue
                if frame == "3":
                    continue

                if frame.startswith("42"):
                    # Socket.io event frame: 42["event_name", {data}]
                    try:
                        parsed = json.loads(frame[2:])
                        event_name = parsed[0]
                        event_data = parsed[1] if len(parsed) > 1 else {}
                        raw_events.append({"event": event_name, "data": event_data})

                        if event_name == "assistant-response":
                            content = event_data.get("content", "")
                            full_text.append(content)
                            print(content, end="", flush=True)
                        elif event_name == "thinkingStateFromServer":
                            thinking_states.append(event_data)
                        elif event_name == "product-recommendations":
                            products.extend(event_data.get("products", []))
                        elif event_name == "follow-up-question":
                            follow_ups.append(event_data)
                        else:
                            print(f"\n[OTHER EVENT: {event_name}] {event_data}", flush=True)
                    except Exception as e:
                        print(f"\n[PARSE ERROR on frame {frame}]: {e}", flush=True)
        except asyncio.TimeoutError:
            pass

        print("\n\n--- COMPLETED ---", flush=True)
        print(f"Total text length: {len(''.join(full_text))} chars", flush=True)
        print(f"Products found: {len(products)}", flush=True)
        if products:
            print("Products:", json.dumps(products, indent=2), flush=True)
        print(f"Follow up questions: {follow_ups}", flush=True)

if __name__ == "__main__":
    asyncio.run(query_kandid("Recommend me the best cleanser and moisturizer for cystic acne"))
