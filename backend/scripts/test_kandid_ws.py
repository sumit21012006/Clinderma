import asyncio
import json
import websockets

WS_URL = "wss://communicate.kandid.ai/socket/?EIO=4&transport=websocket"

QUERY_PAYLOAD = {
    "sessionId": "QphAdfZ6lm-yzk2mrTF8U",
    "agentId": "nz5MJ59H80ZlsN-Y2cb8I",
    "avatarId": "xr7arYZWBbbp26V8ZVoX4",
    "id": 1,
    "kandidShopifyStore": None,
    "path": "/en",
    "query": {
        "type": "TEXT",
        "query": "Hello, I need help with acne"
    }
}

async def test():
    headers = {
        "Origin": "https://communicate.kandid.ai",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    print(f"Connecting to {WS_URL}...", flush=True)
    async with websockets.connect(WS_URL, additional_headers=headers) as ws:
        print("Connected!", flush=True)
        # 1. Recv Engine.IO Handshake
        handshake = await ws.recv()
        print(f"[RECV Handshake] {handshake}", flush=True)

        # 2. Send Socket.IO Connect frame '40'
        print("[SEND Connect] 40", flush=True)
        await ws.send("40")

        # 3. Recv Socket.IO Connect Ack
        ack = await ws.recv()
        print(f"[RECV Connect Ack] {ack}", flush=True)

        # 4. Send the user query event '42["user-query", ...]'
        msg = f'42["user-query",{json.dumps(QUERY_PAYLOAD)}]'
        print(f"[SEND Event] {msg}", flush=True)
        await ws.send(msg)

        msg_count = 0
        try:
            while True:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg_count += 1
                print(f"\n[FRAME #{msg_count}] Length: {len(raw_msg)}", flush=True)
                print(f"[RAW]: {raw_msg[:500]}", flush=True)
                if raw_msg == "2":
                    print("[SEND PONG] 3", flush=True)
                    await ws.send("3")
        except asyncio.TimeoutError:
            print(f"\nStream completed or idle. Total frames received: {msg_count}", flush=True)
        except Exception as e:
            print(f"Recv exception: {e}", flush=True)

if __name__ == "__main__":
    asyncio.run(test())
