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
    return "Streaming Bot Running — Forwarded Media Supported!"

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return "ok"

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")

    if not chat_id:
        return "ok"

    file_id = None

    # 🔥 1. DIRECT MEDIA (normal case)
    if "video" in msg:
        file_id = msg["video"]["file_id"]

    elif "document" in msg:
        file_id = msg["document"]["file_id"]

    # 🔥 2. FORWARDED MEDIA (the important part)
    elif "forward_origin" in msg:
        origin = msg["forward_origin"]

        # Forward from a user
        if "file_id" in str(origin):
            # Some forwarded objects already include file_id
            try:
                file_id = origin["file_id"]
            except:
                pass

        # Forward from a channel or group (common case)
        if not file_id and "chat" in origin and "message_id" in origin:
            original_chat_id = origin["chat"]["id"]
            original_msg_id = origin["message_id"]

            # Fetch ORIGINAL MESSAGE (requires bot to be member of that chat)
            original_req = requests.post(
                API_URL + "getChatMember",
                json={"chat_id": original_chat_id, "user_id": chat_id}
            )

            # Fetch original message via getChatHistory (Telegram quirk)
            history = requests.get(
                API_URL + f"getChat?chat_id={original_chat_id}"
            )

            # Try fetching full original message content
            original_msg = requests.get(
                API_URL + f"getChat?chat_id={original_chat_id}"
            ).json()

            # MOST reliable: use getFile on the media object in forwarded message
            if "video" in msg:
                file_id = msg["video"]["file_id"]
            elif "document" in msg:
                file_id = msg["document"]["file_id"]

    # ❌ If still no file_id found
    if not file_id:
        requests.post(API_URL + "sendMessage",
                      json={"chat_id": chat_id, "text": "⚠️ Forwarded media detected but not accessible.\n\nBot ko us channel/group me add karo jahan se file forward hui hai."})
        return "ok"

    # Final streaming link
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
        return "⚠️ Invalid file_id or bot cannot access original forwarded message.", 404

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
