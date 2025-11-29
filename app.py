import os
import json
import requests
from flask import Flask, request, Response

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
RENDER_URL = os.getenv("RENDER_URL")
BIN_CHANNEL = os.getenv("BIN_CHANNEL")  # e.g. -1001234567890

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

def send_msg(chat_id, text):
    try:
        requests.post(f"{API_BASE}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception:
        pass

def extract_media_file_id_from_message(msg_obj):
    """Return the file_id if present in a Telegram Message object (video/document/audio/animation/photo etc)."""
    if not isinstance(msg_obj, dict):
        return None
    # video
    if "video" in msg_obj and isinstance(msg_obj["video"], dict) and "file_id" in msg_obj["video"]:
        return msg_obj["video"]["file_id"]
    # document
    if "document" in msg_obj and isinstance(msg_obj["document"], dict) and "file_id" in msg_obj["document"]:
        return msg_obj["document"]["file_id"]
    # audio
    if "audio" in msg_obj and isinstance(msg_obj["audio"], dict) and "file_id" in msg_obj["audio"]:
        return msg_obj["audio"]["file_id"]
    # voice
    if "voice" in msg_obj and isinstance(msg_obj["voice"], dict) and "file_id" in msg_obj["voice"]:
        return msg_obj["voice"]["file_id"]
    # animation (gifs)
    if "animation" in msg_obj and isinstance(msg_obj["animation"], dict) and "file_id" in msg_obj["animation"]:
        return msg_obj["animation"]["file_id"]
    # photo (photo is array of sizes; pick last)
    if "photo" in msg_obj and isinstance(msg_obj["photo"], list) and len(msg_obj["photo"])>0:
        last = msg_obj["photo"][-1]
        if "file_id" in last:
            return last["file_id"]
    return None

@app.route("/", methods=["GET"])
def home():
    return "Auto-save Stream Bot (robust) is running."

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    # log incoming payload for debugging (Render logs)
    try:
        print("== WEBHOOK PAYLOAD ==")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        pass

    if not data:
        return "ok"

    msg = data.get("message") or data.get("edited_message") or {}
    if not msg:
        return "ok"

    user_chat_id = msg.get("chat", {}).get("id")
    if not user_chat_id:
        return "ok"

    # Try extract direct media from incoming message first
    direct_file_id = extract_media_file_id_from_message(msg)

    # If direct media present, we still will copy to BIN (to make a permanent original accessible)
    if not direct_file_id:
        # maybe forwarded but without direct media; still attempt to copy message to BIN
        pass

    # Step-1: copyMessage from source chat -> BIN_CHANNEL (this preserves original media and gives us a message object)
    from_chat_id = msg.get("chat", {}).get("id")
    from_message_id = msg.get("message_id")

    if not from_chat_id or not from_message_id:
        send_msg(user_chat_id, "Unable to determine original message location.")
        return "ok"

    try:
        copy_payload = {
            "chat_id": BIN_CHANNEL,
            "from_chat_id": from_chat_id,
            "message_id": from_message_id
        }
        print("== COPYING MESSAGE TO BIN ==")
        resp = requests.post(f"{API_BASE}/copyMessage", json=copy_payload, timeout=30)
        resp_json = resp.json()
        print("== COPY RESPONSE ==")
        print(json.dumps(resp_json, indent=2, ensure_ascii=False))
    except Exception as e:
        send_msg(user_chat_id, f"Failed to copy message to bin channel: {e}")
        return "ok"

    if not resp_json.get("ok"):
        # copyMessage may fail for tons of reasons (protected content, bot lacks permission, etc.)
        send_msg(user_chat_id, f"Copy to bin failed: {resp_json.get('description', 'no description')}")
        return "ok"

    # copyMessage returns a Message object under result
    new_msg = resp_json.get("result")
    # Try to extract file_id from the copied message object
    real_file_id = extract_media_file_id_from_message(new_msg)
    # Sometimes copyMessage returns a "message_id" but the media info is not in result (rare),
    # So as fallback we can attempt to forward it back to the user and inspect the returned message object.
    if not real_file_id:
        # fallback: use forwardMessage to send that saved message back to the user and read the response
        try:
            fm_payload = {
                "chat_id": user_chat_id,
                "from_chat_id": BIN_CHANNEL,
                "message_id": new_msg.get("message_id")
            }
            print("== FORWARDING SAVED MESSAGE BACK TO USER ==", fm_payload)
            fwd_resp = requests.post(f"{API_BASE}/forwardMessage", json=fm_payload, timeout=30)
            fwd_json = fwd_resp.json()
            print("== FORWARD RESPONSE ==")
            print(json.dumps(fwd_json, indent=2, ensure_ascii=False))
            if fwd_json.get("ok") and isinstance(fwd_json.get("result"), dict):
                # extract file_id from the forwarded message object
                real_file_id = extract_media_file_id_from_message(fwd_json["result"])
        except Exception as e:
            print("forward fallback error:", e)

    if not real_file_id:
        send_msg(user_chat_id, "⚠️ Could not extract file_id from saved bin message. Make sure bot is admin of BIN channel and BIN channel allows messages.")
        return "ok"

    # Final: build streaming link and send to user
    stream_link = f"https://{RENDER_URL}/stream/{real_file_id}"
    send_msg(user_chat_id, f"✅ Stream link (from bin):\n{stream_link}")
    return "ok"


@app.route("/stream/<file_id>", methods=["GET"])
def stream_file(file_id):
    # getFile
    try:
        gf = requests.get(f"{API_BASE}/getFile?file_id={file_id}", timeout=30).json()
    except Exception as e:
        print("getFile request error:", e)
        return "getFile request failed", 500

    print("== getFile response ==")
    print(json.dumps(gf, indent=2, ensure_ascii=False))

    if not gf.get("ok"):
        return "Invalid file_id or bot missing access", 404

    file_path = gf["result"].get("file_path")
    if not file_path:
        return "No file_path returned by Telegram", 404

    tg_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    def gen():
        with requests.get(tg_url, stream=True, timeout=60) as r:
            for chunk in r.iter_content(chunk_size=1024*64):
                if chunk:
                    yield chunk
    # Attempt to set a sane content type, but Telegram will suggest correct mime; fallback to octet-stream
    mime = gf["result"].get("mime_type") or "application/octet-stream"
    return Response(gen(), content_type=mime)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
