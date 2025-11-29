import os
import requests
from flask import Flask, request, Response

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
RENDER_URL = os.getenv("RENDER_URL")
BIN_CHANNEL = os.getenv("BIN_CHANNEL")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_URL = f"https://api.telegram.org/file/bot{BOT_TOKEN}/"

app = Flask(__name__)


def extract_file_id(msg):
    """Extract file_id from a message object (video, document, animation, photo)."""
    if "video" in msg:
        return msg["video"]["file_id"]
    if "document" in msg:
        return msg["document"]["file_id"]
    if "animation" in msg:
        return msg["animation"]["file_id"]
    if "photo" in msg:
        return msg["photo"][-1]["file_id"]
    return None


@app.route("/")
def home():
    return "Stream bot running"


@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.json
    msg = data.get("message", {})

    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return "ok"

    message_id = msg.get("message_id")

    # 1️⃣ COPY MESSAGE TO BIN CHANNEL
    copy_res = requests.post(
        f"{API_URL}/copyMessage",
        json={
            "chat_id": BIN_CHANNEL,
            "from_chat_id": chat_id,
            "message_id": message_id
        }
    ).json()

    if not copy_res.get("ok"):
        requests.post(f"{API_URL}/sendMessage",
                      json={"chat_id": chat_id, "text": "Copy to bin failed"})
        return "ok"

    # 2️⃣ GET REAL FILE_ID FROM BIN MESSAGE (CORRECT PLACE)
    bin_msg = copy_res["result"]
    real_file_id = extract_file_id(bin_msg)

    if not real_file_id:
        requests.post(f"{API_URL}/sendMessage",
                      json={"chat_id": chat_id, "text": "Media not found in bin"})
        return "ok"

    # 3️⃣ BUILD STREAM LINK
    stream_link = f"https://{RENDER_URL}/stream/{real_file_id}"

    requests.post(f"{API_URL}/sendMessage",
                  json={"chat_id": chat_id, "text": stream_link})

    return "ok"


@app.route("/stream/<file_id>")
def stream_file(file_id):
    r = requests.get(f"{API_URL}/getFile?file_id={file_id}").json()

    if not r.get("ok"):
        return "Invalid file_id", 404

    file_path = r["result"]["file_path"]
    tg_url = f"{FILE_URL}{file_path}"

    def generate():
        with requests.get(tg_url, stream=True) as s:
            for chunk in s.iter_content(1024 * 64):
                if chunk:
                    yield chunk

    return Response(generate(), content_type="video/mp4")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
