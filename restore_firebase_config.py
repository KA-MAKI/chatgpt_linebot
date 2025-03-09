import os
import json

# 環境変数から Firebase 認証情報を取得
firebase_credentials = os.getenv("GOOGLE_CLOUD_CREDENTIALS")

# 認証情報がない場合はエラーを表示
if not firebase_credentials:
    raise ValueError("🚨 環境変数 'GOOGLE_CLOUD_CREDENTIALS' が設定されていません！Railway の環境変数を確認してください。")

try:
    # JSON 形式にデコード
    credentials_dict = json.loads(firebase_credentials)

    # `service-account.json` に保存
    with open("service-account.json", "w") as f:
        json.dump(credentials_dict, f, indent=4)

    print("✅ Firebase 認証情報を `service-account.json` に復元しました！")

except json.JSONDecodeError as e:
    raise ValueError(f"🚨 Firebase 認証情報の JSON パースに失敗しました: {str(e)}")
