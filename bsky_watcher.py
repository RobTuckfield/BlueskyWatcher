#!/usr/bin/env python3

# bsky watcher - watches a bluesky account for new posts via jetstream
# requires a .env file with BSKY_HANDLE set (see below)

import json
import subprocess
import sys
import time
import os
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

try:
    import websocket
except ImportError:
    print("missing websocket-client, run: pip install websocket-client")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("missing python-dotenv, run: pip install python-dotenv")
    sys.exit(1)

# load config from .env
load_dotenv()

HANDLE = os.getenv("BSKY_HANDLE")
if not HANDLE:
    print("error: BSKY_HANDLE not set in .env file")
    print("create a .env file in this directory with:")
    print('  BSKY_HANDLE=someone.bsky.social')
    sys.exit(1)

HANDLE = HANDLE.lstrip("@")


def clipboard(text):
    """try to copy to clipboard, dont care if it fails"""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except:
        pass
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            return True
        elif sys.platform.startswith("linux"):
            for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["wl-copy"]]:
                try:
                    subprocess.run(cmd, input=text.encode(), check=True)
                    return True
                except FileNotFoundError:
                    continue
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode(), check=True)
            return True
    except:
        pass
    return False


def resolve_did(handle):
    """turn a handle into a DID"""
    url = f"https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle={handle}"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())["did"]
    except HTTPError as e:
        print(f"couldnt resolve handle '{handle}': HTTP {e.code}")
        sys.exit(1)
    except Exception as e:
        print(f"couldnt resolve handle '{handle}': {e}")
        sys.exit(1)


# resolve the handle up front
print(f"resolving @{HANDLE}...")
DID = resolve_did(HANDLE)
print(f"got DID: {DID}")

post_count = 0
last_cursor = None


def on_message(ws, message):
    global post_count, last_cursor
    try:
        event = json.loads(message)
    except:
        return

    last_cursor = event.get("time_us")
    commit = event.get("commit", {})
    op = commit.get("operation") or commit.get("type")
    collection = commit.get("collection", "")

    if collection != "app.bsky.feed.post" or op not in ("create", "c"):
        return

    rkey = commit.get("rkey", "")
    text = commit.get("record", {}).get("text", "")
    url = f"https://bsky.app/profile/{HANDLE}/post/{rkey}"

    post_count += 1
    now = datetime.now().strftime("%H:%M:%S")

    print()
    print(f"{'='*60}")
    print(f"  NEW POST  |  {now}")
    print(f"{'='*60}")
    print(f"  @{HANDLE}")
    print(f"  {text[:200]}{'...' if len(text) > 200 else ''}")
    print(f"  {url}")
    print(f"{'='*60}")

    if clipboard(url):
        print(f"  copied to clipboard")
    print()


def on_error(ws, error):
    print(f"ws error: {error}")


def on_close(ws, code, msg):
    print(f"connection closed (code={code}), reconnecting in 5s...")


def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] connected, watching @{HANDLE}")
    print(f"ctrl+c to stop\n")


# main loop with auto reconnect
print(f"connecting to jetstream...\n")
while True:
    try:
        ws_url = f"wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post&wantedDids={DID}"
        if last_cursor:
            ws_url += f"&cursor={last_cursor - 5_000_000}"

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )
        ws.run_forever(ping_interval=30, ping_timeout=10)
    except KeyboardInterrupt:
        print(f"\nstopped. saw {post_count} post(s).")
        sys.exit(0)
    except:
        pass

    time.sleep(5)
