import os
import requests
from flask import Flask, request, Response

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
RENDER_URL = os.getenv("RENDER_URL")
BIN_CHANNEL = os.getenv("BIN_CHANNEL")  # e.g. -1001234567890

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
FILE_URL = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{{}}"

app = Flask(__name__)


@app.route("/")
def home():
    return "Auto-save Stream Bot Running!"


@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.json
    msg = data.get("message", {})

    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return "ok"

    file_id = None

    # Detect media
    media = None
    if "video" in msg:
        media = msg["video"]
    elif "document" in msg:
        media = msg["document"]

    if not media:
        requests.post(API_URL + "sendMessage",
                      json={"chat_id": chat_id, "text": "Send a video or file."})
        return "ok"

    file_id = media["file_id"]

    # 1️⃣ Auto-forward/upload to BIN CHANNEL
    forward_resp = requests.post(
        API_URL + "copyMessage",
        json={
            "chat_id": BIN_CHANNEL,
            "from_chat_id": chat_id,
            "message_id": msg["message_id"]
        }
    ).json()

    if not forward_resp.get("ok"):
        requests.post(API_URL + "sendMessage",
                      json={"chat_id": chat_id, "text": "Failed to save to bin channel."})
        return "ok"

    # Get NEW message_id from bin channel
    new_msg_id = forward_resp["result"]["message_id"]

    # 2️⃣ Get original message from bin channel
    get_file = requests.post(
        API_URL + "getFile",
        json={"file_id": media["file_id"]}
    ).json()

    # 3️⃣ But best: extract file from BIN channel because bot has full access
    # GET full message in BIN CHANNEL
    orig_msg = requests.post(
        API_URL + "forwardMessage",
        json={
            "chat_id": chat_id,
            "from_chat_id": BIN_CHANNEL,
            "message_id": new_msg_id
        }
    ).json()

    # extract file_id from orig message
    if "video" in orig_msg.get("result", {}):
        real_file_id = orig_msg["result"]["video"]["file_id"]
    elif "document" in orig_msg.get("result", {}):
        real_file_id = orig_msg["result"]["document"]["file_id"]
    else:
        real_file_id = file_id

    # Final stream link
    stream_link = f"https://{RENDER_URL}/stream/{real_file_id}"

    requests.post(API_URL + "sendMessage",
                  json={"chat_id": chat_id, "text": stream_link})

    return "ok"


@app.route("/stream/<file_id>")
def stream_file(file_id):
    r = requests.get(API_URL + f"getFile?file_id={file_id}").json()

    if not r.get("ok"):
        return "Invalid file_id", 404

    file_path = r["result"]["file_path"]
    tg_url = FILE_URL.format(file_path)

    def generate():
        with requests.get(tg_url, stream=True) as s:
            for c in s.iter_content(1024 * 64):
                if c:
                    yield c

    return Response(generate(), content_type="video/mp4")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
