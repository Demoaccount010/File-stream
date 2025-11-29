import os
import requests
from flask import Flask, request, Response

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
RENDER_URL = os.getenv("RENDER_URL")
BIN_CHANNEL = os.getenv("BIN_CHANNEL")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{BOT_TOKEN}/"

app = Flask(__name__)

def extract_real_media(msg):
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
    return "Stream Bot Running"

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.json
    msg = data.get("message", {})

    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")

    # Step 1: COPY TO BIN (always works if admin)
    copy_res = requests.post(
        f"{API}/copyMessage",
        json={
            "chat_id": BIN_CHANNEL,
            "from_chat_id": chat_id,
            "message_id": message_id
        }
    ).json()

    if not copy_res.get("ok"):
        requests.post(f"{API}/sendMessage",
                      json={"chat_id": chat_id, "text": "❌ Copy to BIN failed."})
        return "ok"

    bin_msg = copy_res["result"]

    # Step 2: Extract real media from BIN message
    real_file_id = extract_real_media(bin_msg)

    if not real_file_id:
        requests.post(f"{API}/sendMessage",
                      json={"chat_id": chat_id,
                            "text": "❌ No media in saved message. Bot must be ADMIN in channel!"})
        return "ok"

    # Step 3: Create stream link
    link = f"https://{RENDER_URL}/stream/{real_file_id}"

    requests.post(f"{API}/sendMessage",
                  json={"chat_id": chat_id, "text": link})

    return "ok"

@app.route("/stream/<file_id>")
def stream(file_id):
    file_req = requests.get(f"{API}/getFile?file_id={file_id}").json()
    if not file_req.get("ok"):
        return "Invalid file_id", 404

    file_path = file_req["result"]["file_path"]
    tg_url = FILE_API + file_path

    def gen():
        with requests.get(tg_url, stream=True) as r:
            for c in r.iter_content(1024 * 64):
                if c:
                    yield c

    return Response(gen(), content_type="video/mp4")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
