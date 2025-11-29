
import os, requests
from flask import Flask, request, Response

BOT_TOKEN=os.getenv("BOT_TOKEN")
WEBHOOK_SECRET=os.getenv("WEBHOOK_SECRET")
API_URL=f"https://api.telegram.org/bot{BOT_TOKEN}/"
FILE_URL=f"https://api.telegram.org/file/bot{BOT_TOKEN}/{{}}"

app=Flask(__name__)

@app.route("/",methods=["GET"])
def home():
    return "Render-only Streaming Bot Running!"

@app.route(f"/webhook/{WEBHOOK_SECRET}",methods=["POST"])
def webhook():
    data=request.json
    if not data: return "ok"
    msg=data.get("message",{})
    chat_id=msg.get("chat",{}).get("id")
    if not chat_id: return "ok"

    file_id=None
    if "video" in msg: file_id=msg["video"]["file_id"]
    elif "document" in msg: file_id=msg["document"]["file_id"]
    else:
        requests.post(API_URL+"sendMessage",json={"chat_id":chat_id,"text":"Send video or document"})
        return "ok"

    link=f"https://{os.getenv('RENDER_URL')}/stream/{file_id}"
    requests.post(API_URL+"sendMessage",json={"chat_id":chat_id,"text":link})
    return "ok"

@app.route("/stream/<file_id>")
def stream(file_id):
    r=requests.get(API_URL+f"getFile?file_id={file_id}").json()
    if not r.get("ok"): return "invalid file_id",404
    file_path=r["result"]["file_path"]
    tg_url=FILE_URL.format(file_path)

    def gen():
        with requests.get(tg_url,stream=True) as s:
            for c in s.iter_content(1024*64):
                if c: yield c
    return Response(gen(),content_type="video/mp4")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
