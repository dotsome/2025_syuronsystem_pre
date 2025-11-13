# 実験用システム - 人物関係想起システム

小説を読みながら登場人物について質問でき、自動的に人物関係図（Mermaid図）を生成する実験用Streamlitアプリケーションです。

## 機能

- **3段階認証フロー**
  1. ユーザー名・パスワード認証
  2. ニックネーム・実験ナンバー入力（ファイル名生成用）
  3. メインシステムへアクセス

- **小説閲覧システム**
  - ページごとに小説を表示
  - ナビゲーションボタンで前後のページに移動
  - 指定したページから公開開始（`START_PAGE`で設定可能）

- **質問応答システム**
  - GPT-4を使用した質問応答
  - 既読部分の小説内容に基づいて回答
  - 質問・回答履歴の表示

- **人物関係図自動生成**
  - 登場人物に関する質問を自動判定
  - 2段階プロセスで正確なMermaid図を生成
  - PNG画像として保存・表示

- **ログ記録**
  - ユーザーごとに詳細なログを記録
  - 質問・回答・処理時間などを自動記録
  - ログファイルのダウンロード機能

## 必要な環境

- Python 3.8以上
- Node.js（Mermaid CLI用）
- OpenAI APIキー

## セットアップ

### 1. 必要なパッケージのインストール

```bash
pip install streamlit streamlit-authenticator openai python-dotenv pyyaml
```

### 2. Mermaid CLIのインストール

```bash
npm install -g @mermaid-js/mermaid-cli
```

### 3. 環境変数の設定

`.env`ファイルを作成し、OpenAI APIキーを設定:

```
OPENAI_API_KEY=your_api_key_here
```

### 4. 認証設定

`config.yaml`ファイルで認証情報を設定します。パスワードはハッシュ化が必要です。

`create_yaml.py`を使用してパスワードをハッシュ化できます:

```bash
python create_yaml.py
```

### 5. 小説データの準備

`beast_text.json`ファイルに小説データを配置します。形式:

```json
[
  {
    "section": "1",
    "title": "章タイトル",
    "text": "本文内容"
  },
  ...
]
```

## 使い方

### アプリケーションの起動

```bash
streamlit run zikken_11month_v7.py
```

### 認証フロー

1. **ログイン画面**: `config.yaml`に登録されたユーザー名とパスワードでログイン
2. **プロファイル入力**: ニックネームと実験ナンバーを入力
3. **メインシステム**: 小説閲覧と質問が可能になります

### 小説の閲覧

- 「前へ」「次へ」ボタンでページを移動
- 現在のページ番号が表示されます

### 質問の仕方

- 画面下部の入力欄に質問を入力
- 登場人物に関する質問の場合、自動的に人物関係図が生成されます
- 質問・回答は右側のパネルに履歴として表示されます

## ファイル構成

```
2025_research/
├── zikken_11month_v7.py      # メインアプリケーション
├── config.yaml                # 認証設定
├── create_yaml.py             # パスワードハッシュ化ツール
├── beast_text.json            # 小説データ
├── .env                       # 環境変数（APIキー）
└── zikken_result/             # 出力ディレクトリ
    └── zikken_{nickname}_{number}/
        ├── {nickname}_{number}_chat_log.txt
        ├── {nickname}_{number}_1.mmd
        ├── {nickname}_{number}_1.png
        └── debug_mermaid_1.txt
```

## 出力ファイル

すべての出力は`zikken_result/zikken_{ニックネーム}_{実験ナンバー}/`ディレクトリに保存されます:

- **チャットログ**: `{nickname}_{number}_chat_log.txt`
- **Mermaid図**: `{nickname}_{number}_{質問番号}.mmd`
- **画像**: `{nickname}_{number}_{質問番号}.png`
- **デバッグ情報**: `debug_mermaid_{質問番号}.txt`

## 設定のカスタマイズ

### 公開開始ページの変更

`zikken_11month_v7.py`の以下の行を編集:

```python
START_PAGE = 30  # この値を変更
```

### レイアウトの比率変更

```python
left_col, right_col = st.columns([5, 4])  # [左, 右]の比率
```

### ログレベルの変更

`_build_logger()`関数内でログレベルを調整できます。

## トラブルシューティング

### Mermaid図が生成されない

- `mmdc`コマンドが正しくインストールされているか確認
- エラーメッセージを確認し、Mermaidコードの構文をチェック

### 認証エラー

- `config.yaml`のユーザー名とパスワードが正しいか確認
- パスワードが正しくハッシュ化されているか確認

### APIエラー

- `.env`ファイルにOpenAI APIキーが正しく設定されているか確認
- APIキーの利用制限を確認

## ライセンス

研究用途での使用を想定しています。

## 開発者向け情報

### ログ記録の仕組み

- `@log_io`デコレータで関数の入出力を自動記録
- ContextFilterでユーザー情報と質問番号を自動注入
- RotatingFileHandlerで1MB×5世代のログローテーション

### Mermaid図生成の2段階プロセス

1. GPTで中心人物を特定
2. 中心人物を基にざっくりMermaid図を生成
3. Mermaid図をCSVに変換して検証
4. ルールベースで最終的なMermaid図を構築
5. Mermaid CLIでPNG生成
