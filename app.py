import os
import json
import logging
from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import openai
import firebase_admin
from firebase_admin import credentials, firestore

# ✅ ロギング設定（デバッグ用）
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ 必要な環境変数を取得（Railway で設定済みの前提）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CLOUD_CREDENTIALS = os.getenv("GOOGLE_CLOUD_CREDENTIALS")

# ✅ 環境変数が不足している場合のエラーチェック
missing_vars = []
if not LINE_CHANNEL_ACCESS_TOKEN:
    missing_vars.append("LINE_CHANNEL_ACCESS_TOKEN")
if not LINE_CHANNEL_SECRET:
    missing_vars.append("LINE_CHANNEL_SECRET")
if not OPENAI_API_KEY:
    missing_vars.append("OPENAI_API_KEY")
if not GOOGLE_CLOUD_CREDENTIALS:
    missing_vars.append("GOOGLE_CLOUD_CREDENTIALS")

if missing_vars:
    error_message = f"❌ 環境変数が不足しています: {', '.join(missing_vars)}"
    logger.error(error_message)
    raise ValueError(error_message)

# ✅ Firebase 初期化
try:
    cred = credentials.Certificate(json.loads(GOOGLE_CLOUD_CREDENTIALS))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("✅ Firebase Firestore の初期化成功")
except Exception as e:
    logger.error(f"❌ Firebase 初期化エラー: {e}")
    raise

# ✅ LINE Bot SDK 設定
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ✅ OpenAI API 設定
openai.api_key = OPENAI_API_KEY

# ✅ Flask アプリ設定
app = Flask(__name__)

# ✅ Webhook エンドポイント
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    logger.info(f"📩 受信したリクエスト: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("❌ InvalidSignatureError: 署名が不正です。")
        return "Invalid signature", 400
    except Exception as e:
        logger.error(f"❌ Webhook 処理エラー: {e}")
        return "Internal Server Error", 500

    return "OK", 200

# ✅ LINE からのメッセージイベント処理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    reply_token = event.reply_token

    logger.info(f"📨 ユーザー [{user_id}] のメッセージ: {user_message}")

    # 🔄 Firestore にユーザーのメッセージを保存
    try:
        save_message(user_id, "user", user_message)
    except Exception as e:
        logger.error(f"❌ Firestore 保存エラー（ユーザーメッセージ）: {e}")

    # 🤖 OpenAI API でレスポンスを生成
    ai_response = get_ai_response(user_message)

    # 🔄 Firestore に AI のレスポンスを保存
    try:
        save_message(user_id, "bot", ai_response)
    except Exception as e:
        logger.error(f"❌ Firestore 保存エラー（AI応答）: {e}")

    # 📤 LINE へメッセージを返信
    try:
        line_bot_api.reply_message(reply_token, TextSendMessage(text=ai_response))
        logger.info(f"📤 送信メッセージ: {ai_response}")
    except Exception as e:
        logger.error(f"❌ LINE 返信エラー: {e}")

# ✅ OpenAI API を使用してレスポンスを生成
def get_ai_response(user_input):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "あなたは親切なアシスタントです。"},
                {"role": "user", "content": user_input}
            ],
            max_tokens=100,
            temperature=0.7
        )
        ai_text = response["choices"][0]["message"]["content"].strip()
        logger.info(f"🤖 OpenAI 応答: {ai_text}")
        return ai_text
    except Exception as e:
        logger.error(f"❌ OpenAI API エラー: {e}")
        return "すみません、現在応答を生成できません。"

# ✅ Firestore にメッセージを保存
def save_message(user_id, sender, text):
    try:
        db.collection("messages").add({
            "user_id": user_id,
            "sender": sender,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"✅ Firestore に保存成功: {sender} のメッセージ")
    except Exception as e:
        logger.error(f"❌ Firestore 保存エラー: {e}")

# ✅ ヘルスチェック用エンドポイント
@app.route("/", methods=["GET"])
def health_check():
    return "✅ LINE Bot 稼働中！", 200

# ✅ Flask アプリ起動
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
