import os
import requests
from flask import Flask, request, Response, abort

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
RENDER_URL = os.getenv("RENDER_URL")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
FILE_API = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id="
FILE_URL = f"https://api.telegram.org/file/bot{BOT_TOKEN}/"

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Streaming Bot Running!"

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return "ok"

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")

    if not chat_id:
        return "ok"

    # GET FILE_ID
    if "video" in msg:
        file_id = msg["video"]["file_id"]
    elif "document" in msg:
        file_id = msg["document"]["file_id"]
    else:
        requests.post(API_URL + "sendMessage", json={"chat_id": chat_id, "text": "Send video or document"})
        return "ok"

    stream_link = f"https://{RENDER_URL}/stream/{file_id}"

    requests.post(API_URL + "sendMessage", json={
        "chat_id": chat_id,
        "text": stream_link
    })

    return "ok"


@app.route("/stream/<file_id>")
def stream_file(file_id):
    r = requests.get(FILE_API + file_id).json()

    if not r.get("ok"):
        return "Invalid file_id", 404

    file_path = r["result"]["file_path"]
    tg_url = FILE_URL + file_path

    def generate():
        with requests.get(tg_url, stream=True) as s:
            for chunk in s.iter_content(1024 * 64):
                if chunk:
                    yield chunk

    return Response(generate(), content_type="video/mp4")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
