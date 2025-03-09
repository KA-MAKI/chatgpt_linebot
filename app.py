import os
import json
from flask import Flask, request, jsonify
from google.cloud import firestore
import openai
import requests

app = Flask(__name__)

# 必須環境変数のチェック
REQUIRED_ENV_VARS = [
    "GOOGLE_CLOUD_CREDENTIALS",
    "OPENAI_API_KEY",
    "LINE_CHANNEL_SECRET",
    "LINE_CHANNEL_ACCESS_TOKEN"
]

missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"環境変数が不足しています: {', '.join(missing_vars)}")

# Google Cloud 認証情報を設定
google_credentials = json.loads(os.getenv("GOOGLE_CLOUD_CREDENTIALS"))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/service-account.json"

with open("/app/service-account.json", "w") as f:
    json.dump(google_credentials, f)

db = firestore.Client()
openai.api_key = os.getenv("OPENAI_API_KEY")

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()
    for event in body["events"]:
        if event["type"] == "message" and event["message"]["type"] == "text":
            reply_token = event["replyToken"]
            user_message = event["message"]["text"]

            # OpenAI API で応答生成
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": user_message}]
            )
            bot_reply = response["choices"][0]["message"]["content"]

            # Firestore にログ保存
            db.collection("messages").add({
                "user_message": user_message,
                "bot_reply": bot_reply
            })

            # LINE に返信
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
            payload = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": bot_reply}]
            }
            requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload)

    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
