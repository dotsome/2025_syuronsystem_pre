# 人物関係想起システム - システム概要ドキュメント

## 📖 1. システムの目的

**小説を読みながら登場人物について質問すると、自動的に人物関係図を生成する実験システム**

- 心理学・認知科学の研究用
- 物語を段階的に読む際の「登場人物の関係を思い出す能力」を測定
- 複数の実験条件（6モード）で比較実験が可能

---

## 🔄 2. 画面フロー

```
①認証画面
  ↓
②プロファイル入力（ニックネーム + 実験ナンバー0~5）
  ↓ [タイムスタンプで一意なセッションID生成]
③要約テキスト表示 + 5分タイマー
  ↓
④メインシステム
  ├─ 左側：小説本文 + 質問入力
  └─ 右側：質問履歴 + 回答 + 人物関係図
```

---

## 🎯 3. 実験モード（0-5）の違い

| モード | グラフ | Q&A | 使用章数 | グラフタイプ | 説明 |
|:---:|:---:|:---:|:---:|:---:|---|
| **0** | ✅ | ✅ | 全章 | 中心人物 | **デモモード**（桃太郎） |
| **1** | ✅ | ✅ | 29章 | 中心人物 | X-1章（29章）までの情報で図+回答生成 |
| **2** | ❌ | ❌ | - | - | **質問記録のみ**（図も回答も生成しない） |
| **3** | ✅ | ✅ | 40章 | 中心人物 | Y章（40章）までの情報で図+回答生成（先読み効果測定） |
| **4** | ❌ | ✅ | 29章 | - | **図なし**（回答のみ生成） |
| **5** | ✅ | ✅ | 40章 | **全体図** | 中心人物を特定せず全体の人物関係図を生成 |

**設定パラメータ：**
- X = 30（読者が読み始める章）
- Y = 40（モード3,5で使用する最大章数）

**実装場所：** `zikken_11month_v7.py` (line 29-55)

---

## 💬 4. 質問応答の処理フロー

```
質問入力
  ↓
①質問番号インクリメント + タイムスタンプ記録
  ↓
②現在の章番号を記録（何章目を読んでいるか）
  ↓
③モード2？ YES→記録のみで終了 / NO→続行
  ↓
④コンテキスト範囲を決定（モード別）
  ↓
⑤登場人物質問か判定（GPT-5.1で判定）
  ↓
  YES → 図生成 + 回答生成（並列処理）
  NO  → 回答生成のみ
  ↓
⑥結果を表示 + Google Sheets/Drive に保存
```

**重要な記録項目：**
- 質問時刻（YYYY-MM-DD HH:MM:SS）
- 現在の章番号とタイトル
- 質問内容
- 回答内容
- 人物関係図（Mermaidコード + SVG）

**実装場所：** `zikken_11month_v7.py` (line 1894-2064)

---

## 🎨 5. Mermaid図生成の仕組み（2段階生成）

### ステップ1：中心人物の特定

```python
質問「シドについて教えて」
  ↓ GPT-5.1で抽出
中心人物 = "シド"
```

**実装場所：** `generate_mermaid_file()` (line 1557-1593)

### ステップ2：Structured Outputs で構造化データ生成

```python
# OpenAI Structured Outputs API使用
response_format = CharacterGraph

出力例：
{
  "center_person": "シド",
  "relationships": [
    {
      "source": "シド",
      "target": "アルファ",
      "relation_type": "bidirectional",
      "label": "仲間",
      "group": "シャドウガーデン"
    },
    ...
  ]
}
```

**Pydanticスキーマ定義場所：** (line 688-700)

**実装場所：**
- モード1,3,4（中心人物有り）: line 1636-1674
- モード5（全体図）: line 1599-1635

### ステップ3：Mermaid図の構築

```python
# ルールベース処理で図を構築
- 無効ノード（"不明"など）をフィルタ
- 重複エッジを排除
- ラベルを5文字以内に制限
- 中心人物を金色でハイライト

↓

graph LR
    id_1234["シド"]
    id_5678["アルファ"]
    id_1234 <-->|仲間| id_5678
    style id_1234 fill:#FFD700
```

**実装場所：** `build_mermaid_from_structured()` (line 707-854)

**主な処理：**
1. 無効ノードのフィルタリング（"不明", "主体", "客体"など）
2. 空文字列チェック
3. 重複エッジの排除（同じペア・同じ方向は1つまで）
4. ノードのソート（図の一貫性確保）
5. ラベルの5文字制限
6. subgraphでグループ化
7. 中心人物をゴールド色でハイライト

### ステップ4：Kroki APIでSVG生成

```python
# Mermaidコードを圧縮してエンコード
zlib圧縮 → base64エンコード
  ↓
https://kroki.io/mermaid/svg/{encoded}
  ↓
SVG画像を取得して保存
```

**エンコーディング処理：**
1. Mermaidコード（テキスト）
2. UTF-8でバイト化
3. zlib圧縮（圧縮レベル6）
4. base64でエンコード（URL安全版）
5. Kroki APIのURL末尾に付加
6. HTTPリクエスト実行
7. SVGをレスポンスで取得

**実装場所：** (line 1713-1794)

**失敗時の対応：** 最大3回リトライ（Structured Outputsで再生成）

---

## 💾 6. データ保存先

### 6.1 ローカルファイル

```
zikken_result/
└── zikken_{user}_{num}_{timestamp}/
    ├── {user}_{num}_{timestamp}_chat_log.txt
    ├── {user}_{num}_1.mmd
    ├── {user}_{num}_1.svg
    ├── {user}_{num}_2.mmd
    └── {user}_{num}_2.svg
```

**例：** `zikken_Taro_1_20251211_143022/`

**実装場所：** (line 1201-1209)

**ログファイル詳細：**
- **ファイル**: DEBUG以上を1MB×5世代で保存（RotatingFileHandler）
- **コンソール**: INFO以上
- **本文省略フィルター**: 最初の2行のみ記録（line 451-490）

### 6.2 Google Sheets

**2つのワークシート：**

#### (1) Logsシート（システムログ）
- **レベル**: WARNING以上（API呼び出し削減）
- **バッチ処理**: 10件以上または30秒経過でまとめて書き込み
- **列**: Timestamp | Level | User | Question# | Function | Message

**実装場所：** `GoogleSheetsHandler` (line 365-431)

#### (2) QA_Logs_{実験ナンバー}シート
- **レート制限対策**: 前回書き込みから2秒待機
- **列**:
  - Timestamp
  - User
  - Number
  - Question#
  - **Chapter** ← 質問時に読んでいる章番号
  - **Chapter_Title** ← 質問時に読んでいる章タイトル
  - Question
  - Answer
  - Has_Diagram
  - Mermaid_Code
  - SVG_Content
  - SVG_Drive_Link

**実装場所：** `log_qa()` (line 288-363)

**初期化場所：** (line 1209-1212)

### 6.3 Google Drive

**アップロード対象ファイル：**
- SVG図 (`.svg`)
- Mermaidコード (`.mmd`)

**ファイルサイズ別処理：**
- **5MB未満**: 非resumableアップロード（一括）
- **5MB以上**: resumableアップロード（1MBチャンク、リトライ付き）

**アクセス権限：** 誰でも閲覧可能な直接リンクを生成

**実装場所：** `GoogleDriveUploader` (line 66-238)

---

## ⚡ 7. Prompt Caching最適化

### 7.1 3段階キャッシング戦略

#### (1) Streamlit キャッシュ (`@st.cache_data`)

```python
@st.cache_data
def load_story(demo_mode: bool):
    """小説データをメモリにキャッシュ"""
    ...

@st.cache_data
def prepare_pages(demo_mode: bool, start_page: int):
    """ページデータをメモリにキャッシュ"""
    ...
```

**実装場所：** (line 1240-1276)

#### (2) OpenAI Prompt Caching

**ウォームアップ処理：**
- セッション開始時に1回だけダミー質問を実行
- START_PAGEまでの本文でキャッシュ作成
- character_summary.txtでキャッシュ作成

**実装場所：** `warmup_prompt_cache()` (line 1281-1453)

#### (3) セッション状態キャッシング

```python
def load_character_summary() -> str:
    """character_summary.txtを読み込む"""
    # セッション状態にキャッシュがあればそれを返す
    if "character_summary_cache" in st.session_state:
        return st.session_state.character_summary_cache
    ...
```

**実装場所：** (line 1458-1481)

### 7.2 プロンプト最適化のコツ

```python
# ✅ 良い例：本文を先頭に配置
prompt = f"""
本文:
{story_text}

---

質問: {question}
"""

# ❌ 悪い例：本文が後ろ
prompt = f"""
質問: {question}

本文:
{story_text}
"""
```

**理由：** OpenAI Prompt Cachingは先頭からのプリフィックスをキャッシュするため、変動する部分（質問など）を後ろに配置することでキャッシュ効率が向上

---

## 👥 8. 複数人同時アクセス対応

### 8.1 セッション完全分離

```python
# タイムスタンプで一意化
session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# ディレクトリ名
zikken_{user}_{num}_{timestamp}/

# 例
zikken_alice_1_20251211_143022/  ← アリス
zikken_bob_1_20251211_143023/    ← ボブ（同じ実験ナンバーでも衝突しない）
```

**実装場所：** (line 1065-1073, 1205-1209)

### 8.2 Streamlit セッション状態

```python
init_state("user_name",         "")          # ユーザー別に独立
init_state("user_number",       "")          # ユーザー別に独立
init_state("session_timestamp", "")          # セッション別に一意
init_state("profile_completed", False)       # セッション別に独立
init_state("summary_read",      False)       # セッション別に独立
init_state("question_number",   0)           # セッション別に独立
init_state("chat_history",      [])          # セッション別に独立
```

**実装場所：** (line 964-972)

Streamlitはデフォルトで、ブラウザのセッションごとに`st.session_state`を分離

### 8.3 Google Sheets のマルチユーザー対応

```python
# QA専用ワークシートを実験ナンバー別に作成
worksheet_name = f"QA_Logs_{user_number}"
```

**ワークシート構成：**
```
Google Sheets:
├── Logs (全体ログ)
├── QA_Logs_0 (モード0のユーザー用)
├── QA_Logs_1 (モード1のユーザー用)
├── QA_Logs_2 (モード2のユーザー用)
└── ...
```

**実装場所：** (line 332-339)

### 8.4 レート制限対策

#### Google Sheets 書き込み間隔制御

```python
# レート制限対策: 前回の書き込みから2秒待つ
if hasattr(self, '_last_qa_write'):
    elapsed = time.time() - self._last_qa_write
    if elapsed < 2:
        time.sleep(2 - elapsed)
```

**実装場所：** (line 296-301)

#### バッチ処理による削減

```python
# 10件以上または30秒で一括書き込み
if len(self._buffer) >= 10 or (time.time() - self._last_flush) > 30:
    self._flush_buffer()
```

**実装場所：** (line 393-431)

---

## 🚀 9. 技術的な工夫

### 9.1 並行処理

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=2) as executor:
    # 2つのタスクを並行実行
    diagram_future = executor.submit(generate_mermaid_file, ...)
    answer_future = executor.submit(openai_chat, ...)

    # 両方の結果を取得
    svg_file = diagram_future.result()
    resp = answer_future.result()
```

**効果：** 時間短縮 15-30秒 → 10-20秒程度

**実装場所：** (line 1993-2016)

### 9.2 自動リトライ

#### OpenAI API リトライ

```python
def openai_chat(model: str, messages: list[dict], max_retries: int = 3, **kw):
    """OpenAI APIを呼び出し、500エラー時は自動リトライ"""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(...)
            return response
        except openai.InternalServerError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数バックオフ
                time.sleep(wait_time)
```

**実装場所：** (line 596-682)

#### Kroki API リトライ

- 失敗時に新しいStructured Outputsで再生成
- 最大3回リトライ

**実装場所：** (line 1753-1787)

### 9.3 自動ログ記録

```python
@log_io(mask=400)
def some_function(...):
    """関数の入出力を自動記録"""
    ...
```

**機能：**
- 関数の引数・戻り値を自動記録
- 経過時間を測定
- 本文は省略表示（長文対策）

**実装場所：** (line 542-591)

---

## 📊 10. システムアーキテクチャ

```
┌─────────────────────────┐
│   Streamlit App         │
│  (zikken_11month_v7.py) │
└─────────┬───────────────┘
          │
    ┌─────┼──────┬──────────┬─────────┐
    │     │      │          │         │
    ↓     ↓      ↓          ↓         ↓
  Session OpenAI Google   Google   Kroki
  State   GPT-5.1 Sheets   Drive    API
    │       │      │          │         │
    │       │      │          │         │
    └───────┴──────┴──────────┴─────────┘
            │                 │
      ┌─────┴─────┐    ┌──────┴────────┐
      │ Local     │    │ Cloud         │
      │ Files     │    │ Storage       │
      │ .txt/.svg │    │ Sheets/Drive  │
      └───────────┘    └───────────────┘
```

---

## 📝 11. 使用データ

### 11.1 小説データ（3作品対応）

- `shadow_text.json` (41章) - 陰の実力者になりたくて
- `beast_text.json` (56章) - ビーストテイマー
- `kabi_text.json` (79章) - 田山花袋「蒲団」

**データ形式：**
```json
[
  {
    "section": "1",
    "title": "1章タイトル",
    "text": "本文..."
  },
  {
    "section": "2",
    "title": "2章タイトル",
    "text": "本文..."
  },
  ...
]
```

**選択方法：** `NOVEL_FILE`変数で指定（line 60）

### 11.2 登場人物情報ファイル

- `character_summary.txt` - 本番用
- `character_summary_DEMO.txt` - デモ用

**内容：**
```
================================================================================
登場人物を網羅したあらすじ
================================================================================

## 登場人物一覧

### 主人公とその仲間

- **レイン・シュラウド**
  - 立場: 主人公。元・勇者パーティーの一員。
  - 職業・能力: ビーストテイマー（動物使役）
  ...
```

---

## 🔧 12. 環境設定

### 12.1 必須の環境変数

#### OpenAI API Key

```bash
# .envファイル
OPENAI_API_KEY=sk-...
```

または

```toml
# Streamlit Secrets
OPENAI_API_KEY = "sk-..."
```

**読み込み場所：** (line 1216-1227)

### 12.2 Google Cloud 設定（オプション）

#### Google Sheets

```toml
# Streamlit Secrets
google_spreadsheet_key = "1ABC..."
```

#### Google Drive

```toml
# Streamlit Secrets
google_drive_folder_id = "1XYZ..."

[gcp_service_account]
type = "service_account"
project_id = "your-project"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
...
```

### 12.3 認証設定

#### config.yaml（ローカル開発用）

```yaml
credentials:
  usernames:
    user1:
      email: user1@example.com
      name: User One
      password: $2b$12$...  # bcryptハッシュ
    user2:
      email: user2@example.com
      name: User Two
      password: $2b$12$...
cookie:
  name: auth_cookie
  key: random_signature_key
  expiry_days: 30
```

または Streamlit Secrets で設定可能

**読み込み場所：** (line 974-1016)

---

## 📦 13. 依存パッケージ

```
streamlit
openai
python-dotenv
streamlit-authenticator
pyyaml
gspread
oauth2client
google-api-python-client
google-auth
google-auth-httplib2
google-auth-oauthlib
pydantic
requests
```

---

## 🚀 14. デプロイ方法

### Streamlit Cloud へのデプロイ

1. GitHubリポジトリにプッシュ
2. Streamlit Cloudで新しいアプリを作成
3. Secretsに環境変数を設定：
   - `OPENAI_API_KEY`
   - `google_spreadsheet_key`（オプション）
   - `google_drive_folder_id`（オプション）
   - `gcp_service_account`（オプション）
   - 認証情報（`credentials`, `cookie`）

4. デプロイ完了

---

## 📖 15. 使い方

### 開発者向け（ローカル実行）

```bash
# 1. 環境変数を設定
cp .env.example .env
# .envファイルを編集してOPENAI_API_KEYを設定

# 2. 認証設定
# config.yamlを作成（または.streamlit/secrets.tomlに設定）

# 3. 実行
streamlit run zikken_11month_v7.py
```

### 実験参加者向け

1. システムにアクセス
2. ユーザー名・パスワードでログイン
3. ニックネームと実験ナンバー（0-5）を入力
4. 要約テキストを5分間読む
5. 小説を読みながら質問
   - 登場人物に関する質問 → 人物関係図が自動生成
   - その他の質問 → 回答のみ生成

---

## 🐛 16. トラブルシューティング

### Q1. "OPENAI_API_KEY が設定されていません" エラー

**原因：** 環境変数が読み込めていない

**解決方法：**
- ローカル: `.env`ファイルを作成してAPIキーを設定
- Streamlit Cloud: Secretsに`OPENAI_API_KEY`を追加

### Q2. Google Sheets/Drive にデータが保存されない

**原因：** Secrets が設定されていない

**解決方法：**
- `google_spreadsheet_key`を設定
- `gcp_service_account`の全フィールドを設定
- サービスアカウントに権限を付与

### Q3. Mermaid図生成に失敗する

**原因：** Kroki APIの一時的な障害またはネットワークエラー

**解決方法：**
- システムが自動的に3回リトライ
- それでも失敗する場合はMermaidコードが表示される
- ログを確認して詳細を調査

### Q4. 複数人が同じユーザー名で同時アクセスすると衝突する？

**回答：** いいえ、衝突しません

**理由：** タイムスタンプでセッションIDを一意化しているため、同じユーザー名+実験ナンバーでも完全に分離されます

---

## 📚 17. 参考資料

### コード構成

| ファイル | 行数 | 説明 |
|---------|-----|------|
| `zikken_11month_v7.py` | 2,078行 | メインプログラム |
| `shadow_text.json` | - | 小説データ（陰の実力者） |
| `beast_text.json` | - | 小説データ（ビーストテイマー） |
| `kabi_text.json` | - | 小説データ（蒲団） |
| `character_summary.txt` | - | 登場人物情報 |

### 主要な関数・クラス

| 名前 | 場所 | 説明 |
|-----|-----|------|
| `get_mode_config()` | line 45-55 | 実験モード設定を取得 |
| `GoogleDriveUploader` | line 66-238 | Google Driveアップロード |
| `GoogleSheetsLogger` | line 241-286 | Google Sheetsログ記録 |
| `StoryTextFilter` | line 451-490 | 本文省略フィルター |
| `openai_chat()` | line 596-682 | OpenAI API呼び出し（リトライ付き） |
| `CharacterGraph` | line 688-700 | Pydanticスキーマ |
| `build_mermaid_from_structured()` | line 707-854 | Mermaid図構築 |
| `is_character_question()` | line 1487-1528 | 登場人物質問の判定 |
| `generate_mermaid_file()` | line 1534-1794 | Mermaid図生成（2段階） |
| `warmup_prompt_cache()` | line 1281-1453 | Prompt Cachingウォームアップ |

---

## 📄 ライセンス

このシステムは研究・教育目的で開発されています。

---

**最終更新日：** 2024-12-11
**バージョン：** v7
**メンテナー：** システム開発チーム
