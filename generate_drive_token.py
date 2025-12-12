"""
Google Drive OAuth認証トークンを生成するスクリプト
ローカル環境で1回だけ実行してtoken.jsonを生成する
"""
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import json
import os

# スコープ設定
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def generate_token():
    """OAuth認証を行い、トークンを生成"""

    # credentials.jsonが必要（Google Cloud Consoleからダウンロード）
    if not os.path.exists('credentials.json'):
        print("❌ credentials.jsonが見つかりません")
        print("Google Cloud Consoleから以下の手順でダウンロードしてください：")
        print("1. https://console.cloud.google.com/ にアクセス")
        print("2. プロジェクトを選択")
        print("3. 「APIとサービス」→「認証情報」")
        print("4. 「OAuth 2.0 クライアントID」を作成（デスクトップアプリ）")
        print("5. JSONをダウンロードして credentials.json として保存")
        return

    # OAuth認証フロー
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)

    # トークンを保存
    with open('token.json', 'w') as token_file:
        token_file.write(creds.to_json())

    print("✅ token.json が生成されました")
    print("\n次のステップ:")
    print("1. token.json の内容をコピー")
    print("2. Streamlit Cloud の Secrets に以下の形式で追加:")
    print("\n[google_drive_oauth]")

    # トークンの内容を表示
    with open('token.json', 'r') as f:
        token_data = json.load(f)
        for key, value in token_data.items():
            if isinstance(value, str):
                print(f'{key} = "{value}"')
            else:
                print(f'{key} = {json.dumps(value)}')

if __name__ == '__main__':
    generate_token()
