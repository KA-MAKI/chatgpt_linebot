import os
import json
import logging
import openai
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# **📌 ログ設定（エラー検出を強化）**
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# **📌 環境変数の取得（Railway の環境変数を利用）**
GOOGLE_CLOUD_CREDENTIALS = os.getenv("GOOGLE_CLOUD_CREDENTIALS")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# **📌 必須環境変数のチェック**
missing_vars = []
if not GOOGLE_CLOUD_CREDENTIALS:
    missing_vars.append("GOOGLE_CLOUD_CREDENTIALS")
if not LINE_CHANNEL_ACCESS_TOKEN:
    missing_vars.append("LINE_CHANNEL_ACCESS_TOKEN")
if not LINE_CHANNEL_SECRET:
    missing_vars.append("LINE_CHANNEL_SECRET")
if not OPENAI_API_KEY:
    missing_vars.append("OPENAI_API_KEY")

if missing_vars:
    raise ValueError(f"環境変数が不足しています: {', '.join(missing_vars)}")

# **📌 Firebase 初期化**
try:
    cred = credentials.Certificate(json.loads(GOOGLE_CLOUD_CREDENTIALS))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("✅ Firebase 初期化成功")
except Exception as e:
    logger.error(f"❌ Firebase 初期化エラー: {e}")
    raise e

# **📌 LINE Bot API & WebhookHandler 初期化**
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# **📌 Flask アプリの作成**
app = Flask(__name__)

# **📌 ルートエンドポイント（動作確認用）**
@app.route("/", methods=["GET"])
def home():
    return "✅ LINE Bot is running!", 200

# **📌 LINE Webhook エンドポイント**
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    
    logger.info(f"📩 Webhook received: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("❌ Invalid LINE Signature")
        return "Invalid signature", 400
    except Exception as e:
        logger.error(f"❌ Webhook処理エラー: {e}")
        return "Internal Server Error", 500

    return "OK", 200

# **📌 メッセージイベント処理**
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    logger.info(f"📩 受信メッセージ: {user_message} from {user_id}")

    # **📌 Firestore にメッセージを保存**
    try:
        doc_ref = db.collection("messages").document()
        doc_ref.set({
            "user_id": user_id,
            "message": user_message,
            "response": None,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        logger.info("✅ Firestore にメッセージ保存成功")
    except Exception as e:
        logger.error(f"❌ Firestore 保存エラー: {e}")

    # **📌 OpenAI API で返信を生成**
    response_text = generate_openai_response(user_message)

    # **📌 Firestore に返信を保存**
    try:
        doc_ref.update({"response": response_text})
        logger.info("✅ Firestore に返信保存成功")
    except Exception as e:
        logger.error(f"❌ Firestore 更新エラー: {e}")

    # **📌 LINE に返信を送信**
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_text))
        logger.info("✅ LINE 返信成功")
    except Exception as e:
        logger.error(f"❌ LINE 返信エラー: {e}")

# **📌 OpenAI の応答を生成する関数**
def generate_openai_response(user_input):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "あなたは親切な AI アシスタントです。"},
                      {"role": "user", "content": user_input}],
            api_key=OPENAI_API_KEY
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"❌ OpenAI API エラー: {e}")
        return "エラーが発生しました。しばらくしてから再試行してください。"

# **📌 アプリ実行**
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
