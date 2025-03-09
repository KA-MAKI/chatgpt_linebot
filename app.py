import os
import json
import base64
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify
import openai
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# **📌 ログ設定**
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# **📌 環境変数の取得**
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CLOUD_CREDENTIALS = os.getenv("GOOGLE_CLOUD_CREDENTIALS")

# **📌 環境変数チェック**
if not LINE_CHANNEL_ACCESS_TOKEN:
    raise ValueError("❌ 環境変数 `LINE_CHANNEL_ACCESS_TOKEN` が設定されていません！")

if not LINE_CHANNEL_SECRET:
    raise ValueError("❌ 環境変数 `LINE_CHANNEL_SECRET` が設定されていません！")

if not OPENAI_API_KEY:
    raise ValueError("❌ 環境変数 `OPENAI_API_KEY` が設定されていません！")

if not GOOGLE_CLOUD_CREDENTIALS:
    raise ValueError("❌ 環境変数 `GOOGLE_CLOUD_CREDENTIALS` が設定されていません！")

# **📌 Firebase 認証（Base64 デコード + JSON 変換）**
try:
    decoded_json = base64.b64decode(GOOGLE_CLOUD_CREDENTIALS).decode("utf-8")
    credentials_json = json.loads(decoded_json)
    cred = credentials.Certificate(credentials_json)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("✅ Firebase 初期化成功！")
except Exception as e:
    logger.error(f"❌ Firebase 初期化エラー: {e}")
    raise e

# **📌 Flask アプリ作成**
app = Flask(__name__)

# **📌 LINE Bot API 設定**
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# **📌 OpenAI API 設定**
openai.api_key = OPENAI_API_KEY

@app.route("/", methods=["GET"])
def home():
    return "✅ LINE Bot is running!", 200

# **📌 LINE Webhook エンドポイント**
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("❌ InvalidSignatureError: LINE Channel Secret が間違っている可能性あり")
        return "Invalid signature", 400

    return "OK", 200

# **📌 メッセージイベント処理**
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    reply_token = event.reply_token

    # **📌 Firestore にログ保存**
    try:
        doc_ref = db.collection("messages").document()
        doc_ref.set({
            "user_id": user_id,
            "user_message": user_message,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"✅ Firestore にメッセージ保存成功: {user_message}")
    except Exception as e:
        logger.error(f"❌ Firestore 保存エラー: {e}")

    # **📌 OpenAI API で応答生成**
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": user_message}]
        )
        bot_reply = response["choices"][0]["message"]["content"].strip()
        logger.info(f"✅ OpenAI 返信生成成功: {bot_reply}")
    except Exception as e:
        logger.error(f"❌ OpenAI API エラー: {e}")
        bot_reply = "申し訳ありません。現在システムが利用できません。"

    # **📌 LINE に返信**
    try:
        line_bot_api.reply_message(reply_token, TextSendMessage(text=bot_reply))
        logger.info(f"✅ LINE 返信成功: {bot_reply}")
    except Exception as e:
        logger.error(f"❌ LINE 返信エラー: {e}")

# **📌 アプリ起動**
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
