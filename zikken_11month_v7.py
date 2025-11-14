# ===============================================
#  実験用システム（改良版）
#          ── 2段階Mermaid生成システム ──
# ===============================================
import os, json, subprocess, logging, re, time, csv
from pathlib import Path
from functools import wraps
from logging.handlers import RotatingFileHandler
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv
import openai
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =================================================
#                 ページ設定
# =================================================
# Note: st.set_page_config() must be the first Streamlit command
st.set_page_config(page_title="人物関係想起システム",
                   page_icon="📖", layout="wide")

# -------------------------------------------------
# 公開を開始するページ（0-index）
# -------------------------------------------------
START_PAGE = 30 #START_PAGE+1ページから読者が読み進めます

# =================================================
#                🔸  ロガー関連
# =================================================
class GoogleSheetsLogger:
    """Google Sheetsにログを出力するクラス（ロギングハンドラーとQAログ用）"""
    _instance = None

    def __new__(cls, spreadsheet_key: str):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.spreadsheet_key = spreadsheet_key
            cls._instance.client = None
            cls._instance.spreadsheet = None
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        """Google Sheetsクライアントを初期化"""
        try:
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                scope = ['https://spreadsheets.google.com/feeds',
                        'https://www.googleapis.com/auth/drive']
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                self.client = gspread.authorize(creds)
                self.spreadsheet = self.client.open_by_key(self.spreadsheet_key)
                st.success(f"✅ Google Sheets接続成功")
            else:
                st.warning("⚠️ gcp_service_account がsecretsに見つかりません")
        except Exception as e:
            error_msg = f"Google Sheets初期化エラー: {e}"
            print(error_msg)
            st.error(error_msg)
            import traceback
            st.code(traceback.format_exc())

    def get_or_create_worksheet(self, worksheet_name: str, headers: list = None):
        """ワークシートを取得または作成"""
        if self.spreadsheet is None:
            return None

        try:
            worksheet = self.spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title=worksheet_name, rows=1000, cols=20)
            if headers:
                worksheet.append_row(headers)
        return worksheet

    def log_qa(self, user_name: str, user_number: str, q_num: int,
               question: str, answer: str, mermaid_code: str = None,
               svg_path: str = None):
        """質問・回答・図をGoogle Sheetsに記録（レート制限対策付き）"""
        if self.spreadsheet is None:
            return

        try:
            # レート制限対策: 前回の書き込みから2秒待つ
            if hasattr(self, '_last_qa_write'):
                elapsed = time.time() - self._last_qa_write
                if elapsed < 2:
                    time.sleep(2 - elapsed)

            # QA専用ワークシートを取得/作成
            worksheet = self.get_or_create_worksheet(
                "QA_Logs",
                headers=["Timestamp", "User", "Number", "Question#",
                        "Question", "Answer", "Has_Diagram", "Mermaid_Code", "SVG_Path"]
            )

            if worksheet:
                row_data = [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    user_name,
                    user_number,
                    str(q_num),
                    question,
                    answer,
                    "Yes" if mermaid_code else "No",
                    mermaid_code if mermaid_code else "",
                    svg_path if svg_path else ""
                ]
                worksheet.append_row(row_data)
                self._last_qa_write = time.time()
        except Exception as e:
            error_msg = f"QAログ書き込みエラー: {e}"
            print(error_msg)
            # レート制限エラーの場合は、ユーザーに通知しない（サイレント）
            if "429" not in str(e) and "Quota exceeded" not in str(e):
                st.warning(f"⚠️ QAログの記録に失敗しました: {e}")

class GoogleSheetsHandler(logging.Handler):
    """Google Sheetsにログを出力するハンドラー（既存のログ用）"""
    def __init__(self, spreadsheet_key: str, worksheet_name: str = "Logs"):
        super().__init__()
        self.spreadsheet_key = spreadsheet_key
        self.worksheet_name = worksheet_name
        self.worksheet = None
        self.sheets_logger = GoogleSheetsLogger(spreadsheet_key)
        self._init_worksheet()

    def _init_worksheet(self):
        """Google Sheetsワークシートを初期化（既存のログ用）"""
        try:
            # GoogleSheetsLoggerを使用してワークシートを取得
            self.worksheet = self.sheets_logger.get_or_create_worksheet(
                self.worksheet_name,
                headers=["Timestamp", "Level", "User", "Question#", "Function", "Message"]
            )
        except Exception as e:
            error_msg = f"Logsワークシート初期化エラー: {e}"
            print(error_msg)
            self.worksheet = None

    def emit(self, record):
        """ログレコードをGoogle Sheetsに書き込む（バッファリング）"""
        if self.worksheet is None:
            return

        # バッファに追加（バッチ書き込みのため）
        if not hasattr(self, '_buffer'):
            self._buffer = []
            self._last_flush = time.time()

        try:
            log_entry = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                record.levelname,
                getattr(record, 'user', '-'),
                str(getattr(record, 'q_num', 0)),
                record.funcName,
                self.format(record)
            ]
            self._buffer.append(log_entry)

            # 10件以上溜まったら、または30秒経過したらフラッシュ
            if len(self._buffer) >= 10 or (time.time() - self._last_flush) > 30:
                self._flush_buffer()
        except Exception as e:
            error_msg = f"Google Sheetsログバッファエラー: {e}"
            print(error_msg)
            if not hasattr(self, '_error_shown'):
                # エラー表示は最初の1回のみ（UIを汚さないため）
                self._error_shown = True

    def _flush_buffer(self):
        """バッファの内容を一括書き込み"""
        if not hasattr(self, '_buffer') or not self._buffer:
            return

        try:
            # バッチで書き込み（1回のAPI呼び出しで複数行）
            self.worksheet.append_rows(self._buffer)
            self._buffer = []
            self._last_flush = time.time()
        except Exception as e:
            print(f"Google Sheetsバッチ書き込みエラー: {e}")
            self._buffer = []  # エラー時もバッファをクリア

def _build_logger(log_path: Path) -> logging.Logger:
    """
    ・ファイル      : DEBUG 以上を 1 MB × 5 世代で保存
    ・コンソール    : INFO 以上
    ・ContextFilter : user / q_num を自動注入
    """
    class ContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.user  = st.session_state.get("user_name", "-")
            record.q_num = st.session_state.get("question_number", 0)
            return True

    class StoryTextFilter(logging.Filter):
        """本文を省略するフィルター"""
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()

            # 本文（参考）を含む場合は省略
            if "本文（参考）:" in msg or "本文ここから" in msg:
                # 本文部分を検出して省略
                lines = msg.split('\n')
                filtered_lines = []
                story_section = False
                story_line_count = 0

                for line in lines:
                    if "本文（参考）:" in line or "本文ここから" in line:
                        story_section = True
                        filtered_lines.append(line)
                        filtered_lines.append("【本文省略 - 詳細はストーリーファイルを参照】")
                        story_line_count = 0
                        continue

                    if story_section:
                        story_line_count += 1
                        # 最初の2行だけ表示
                        if story_line_count <= 2:
                            filtered_lines.append(line)
                        elif story_line_count == 3:
                            filtered_lines.append("...")
                        # 終了マーカーを検出
                        if "本文ここまで" in line or "---" in line:
                            story_section = False
                            if story_line_count > 3:
                                filtered_lines.append(line)
                    else:
                        filtered_lines.append(line)

                record.msg = '\n'.join(filtered_lines)
                record.args = ()

            return True

    fmt_file = "%(asctime)s [%(levelname)s] U:%(user)s Q:%(q_num)s %(funcName)s: %(message)s"
    fmt_term = "%(asctime)s [%(levelname)s] %(message)s"

    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG)

    # FileHandler
    h_file = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    h_file.setFormatter(logging.Formatter(fmt_file))
    h_file.setLevel(logging.DEBUG)
    h_file.addFilter(ContextFilter())
    h_file.addFilter(StoryTextFilter())  # 本文省略フィルターを追加
    logger.addHandler(h_file)

    # Console
    h_term = logging.StreamHandler()
    h_term.setFormatter(logging.Formatter(fmt_term))
    h_term.setLevel(logging.INFO)
    h_term.addFilter(ContextFilter())
    h_term.addFilter(StoryTextFilter())  # 本文省略フィルターを追加
    logger.addHandler(h_term)

    # Google Sheets Handler (Streamlit Cloudで有効)
    # 注: レート制限対策のため、WARNINGレベル以上のみをGoogle Sheetsに記録
    # 詳細ログはファイルに記録され、QAログは別途log_qa()で記録される
    try:
        if "google_spreadsheet_key" in st.secrets:
            h_sheets = GoogleSheetsHandler(
                spreadsheet_key=st.secrets["google_spreadsheet_key"],
                worksheet_name="Logs"  # 固定のワークシート名を使用
            )
            h_sheets.setFormatter(logging.Formatter("%(message)s"))
            h_sheets.setLevel(logging.WARNING)  # INFO→WARNINGに変更してAPI呼び出しを削減
            h_sheets.addFilter(ContextFilter())
            logger.addHandler(h_sheets)
    except Exception as e:
        error_msg = f"Google Sheetsハンドラー追加エラー: {e}"
        print(error_msg)
        # エラーは表示しない（起動時のノイズを減らす）

    logger.propagate = False
    return logger

# -------------------------------------------------
# デコレータ：入出力＆経過時間を自動記録
# -------------------------------------------------
def log_io(mask: int | None = 400):
    """
    mask=None なら全文、数値ならその文字数だけログに残す
    """
    def _decorator(func):
        @wraps(func)
        def _wrapper(*args, **kwargs):
            t0 = time.time()
            logger = logging.getLogger("app")
            logger.debug(f"[IN ] {func.__name__} args={args} kwargs={kwargs}")
            try:
                out = func(*args, **kwargs)
                elapsed = time.time() - t0
                if mask is None:
                    out_str = str(out)
                else:
                    out_str = (str(out)[:mask] + "...") if isinstance(out, str) else str(out)
                logger.debug(f"[OUT] {func.__name__} ({elapsed:.2f}s) -> {out_str}")
                return out
            except Exception:
                logger.exception(f"[ERR] {func.__name__}")
                raise
        return _wrapper
    return _decorator

# -------------------------------------------------
# OpenAI 呼び出しラッパ（処理時間計測付き）
# -------------------------------------------------
def openai_chat(model: str, messages: list[dict], log_label: str = None, **kw):
    """
    OpenAI APIを呼び出し、処理時間を計測してログに記録

    Args:
        model: 使用するモデル名
        messages: メッセージリスト
        log_label: ログに記録するラベル（例: "質問判定", "中心人物特定"）
        **kw: その他のパラメータ
    """
    logger = logging.getLogger("app")

    # プロンプトの長さを計算
    total_chars = sum(len(str(msg.get('content', ''))) for msg in messages)

    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kw
        )
        elapsed = time.time() - start_time

        # トークン使用量を取得
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        # ログに記録
        log_msg = f"🤖 LLM呼び出し"
        if log_label:
            log_msg += f" [{log_label}]"
        log_msg += f": model={model}, time={elapsed:.2f}s, prompt_chars={total_chars}, tokens={prompt_tokens}→{completion_tokens} (total={total_tokens})"

        logger.info(log_msg)

        return response
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ LLM呼び出し失敗 [{log_label}]: model={model}, time={elapsed:.2f}s, error={str(e)}")
        raise

# =================================================
#           Streamlit セッション初期化
# =================================================
def init_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

init_state("user_name",        "")
init_state("user_number",      "")
init_state("profile_completed", False)  # プロファイル入力完了フラグ
init_state("question_number",  0)
init_state("ui_page",          0)   # UI 上でのページ（0 … START_PAGE）
init_state("messages", [
    {"role": "system",
     "content": "あなたは読んでいる小説について質問に答えるアシスタントです。"}
])
init_state("chat_history",     [])

# =================================================
#               認証設定
# =================================================
# Streamlit Cloud環境ではst.secretsから、ローカルではconfig.yamlから読み込む
config = None

def secrets_to_dict(secrets_obj):
    """Streamlit Secretsオブジェクトを再帰的に通常の辞書に変換"""
    if hasattr(secrets_obj, 'to_dict'):
        return secrets_obj.to_dict()
    elif isinstance(secrets_obj, dict):
        return {k: secrets_to_dict(v) for k, v in secrets_obj.items()}
    else:
        return secrets_obj

# まずStreamlit Secretsを試す
try:
    config = secrets_to_dict(st.secrets["auth"])
except (FileNotFoundError, KeyError):
    pass

# Secretsが無い場合はconfig.yamlを試す
if config is None:
    yaml_path = "config.yaml"
    try:
        with open(yaml_path) as file:
            config = yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        st.error("""
        ⚠️ 認証設定が見つかりません

        **Streamlit Cloudをご利用の場合:**
        - App Settings > Secrets に認証情報を設定してください
        - `.streamlit/secrets.toml.example` を参考にしてください

        **ローカル環境の場合:**
        - `config.yaml` ファイルを作成してください
        - `create_yaml.py` を実行してパスワードをハッシュ化できます
        """)
        st.stop()

if config is None:
    st.error("認証設定の読み込みに失敗しました")
    st.stop()

authenticator = stauth.Authenticate(
    credentials=config['credentials'],
    cookie_name=config['cookie']['name'],
    cookie_key=config['cookie']['key'],
    cookie_expiry_days=config['cookie']['expiry_days'],
)

# =================================================
#               認証処理
# =================================================
authenticator.login()

if st.session_state["authentication_status"] is False:
    # ログイン失敗
    st.error('Username/password is incorrect')
    st.stop()

elif st.session_state["authentication_status"] is None:
    # 未認証
    st.warning('Please enter your username and password')
    st.stop()

elif st.session_state["authentication_status"]:
    # ログイン成功 - サイドバーにログアウトボタンを追加
    with st.sidebar:
        st.markdown(f'## Welcome *{st.session_state["name"]}*')
        authenticator.logout('Logout', 'sidebar')
        st.divider()

    # プロファイル入力が完了していない場合、プロファイル入力画面を表示
    if not st.session_state.profile_completed:
        st.title("📝 プロファイル入力")
        st.markdown("### 実験参加情報を入力してください")

        with st.form("profile_form"):
            nickname = st.text_input("ニックネーム",
                                     placeholder="例: Taro",
                                     help="ファイル名に使用されます")
            experiment_number = st.text_input("実験ナンバー",
                                              placeholder="例: EXP001",
                                              help="ファイル名に使用されます")
            submitted = st.form_submit_button("次へ")

            if submitted:
                if nickname and experiment_number:
                    st.session_state.user_name = nickname
                    st.session_state.user_number = experiment_number
                    st.session_state.profile_completed = True
                    st.success("プロファイル設定完了!")
                    st.rerun()
                else:
                    st.error("ニックネームと実験ナンバーの両方を入力してください")

        # プロファイル入力画面ではここで停止
        st.stop()

# =================================================
#          🔸 ユーザー別ディレクトリ & ログ
# =================================================
# zikken_result ディレクトリの作成
base_dir = Path("zikken_result")
base_dir.mkdir(exist_ok=True)

# ユーザー別ディレクトリを zikken_result 配下に作成
user_dir = base_dir / f"zikken_{st.session_state.user_name}_{st.session_state.user_number}"
user_dir.mkdir(exist_ok=True)

log_file = user_dir / f"{st.session_state.user_name}_{st.session_state.user_number}_chat_log.txt"
logger   = _build_logger(log_file)
logger.info("--- Session started ---")

# Google Sheets QAロガーの初期化（Streamlit Cloudで有効）
sheets_qa_logger = None
if "google_spreadsheet_key" in st.secrets:
    sheets_qa_logger = GoogleSheetsLogger(st.secrets["google_spreadsheet_key"])

# =================================================
#          OpenAI クライアント初期化
# =================================================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY が設定されていません。")
    st.stop()

client = openai.OpenAI(api_key=api_key)

st.title("📖 人物関係想起システム")

# =================================================
#              小説データ読み込み
# =================================================
@st.cache_data
@log_io()                 # 読み込み状況も記録
def load_story(filename="beast_text.json"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        st.warning("⚠️ beast_text.json が見つかりません。ダミーデータを使用します。")
        return [
            {"section": "1", "title": "序章",
             "text": "これは物語の始まりです。主人公の太郎は、異世界に転生しました。"},
            {"section": "2", "title": "出会い",
             "text": "太郎は森で不思議な獣と出会いました。その獣の名前はシロと言いました。"}
        ]

story_sections = load_story()
pages_all = [f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
             for sec in story_sections]
pages_ui       = pages_all[START_PAGE:]
total_ui_pages = len(pages_ui)
total_pages    = len(pages_all)

# =================================================
# GPT 4o：登場人物質問の判定
# =================================================
@log_io()
def is_character_question(question: str) -> bool:
    prompt = f"以下の質問が『登場人物』に関するものか Yes / No で答えてください。\n\n質問: {question}"
    try:
        res = openai_chat(
            "gpt-4o",
            messages=[
                {"role": "system", "content": "質問が登場人物に関するか判定します。"},
                {"role": "user",   "content": prompt}
            ],
            temperature=0,
            log_label="登場人物質問判定"
        )
        answer = res.choices[0].message.content.strip().lower()
        return "yes" in answer
    except Exception:
        logger.exception("is_character_question Error")
        return False

# =================================================
# 改良版 Mermaid 図生成（2段階プロセス）
# =================================================
@log_io(mask=None)
def generate_mermaid_file(question: str, story_text: str, q_num: int) -> str | None:
    """
    2段階プロセス：
    1. GPTでざっくりMermaid図を生成
    2. それをCSVに変換して検証
    3. ルールベースで最終的なMermaid図を構築
    """
    # ──────────────────────────
    # Step 1: 質問の中心人物を特定
    # ──────────────────────────
    who_prompt = f"""
質問「{question}」の中心となる登場人物の名前を1つだけ答えてください。
本文に登場する人物名で答えること。

本文（冒頭）:
{story_text[:1000]}
"""
    
    try:
        res_who = openai_chat(
            "gpt-4o",
            messages=[
                {"role": "system", "content": "質問の中心人物を特定します。"},
                {"role": "user", "content": who_prompt}
            ],
            temperature=0,
            log_label="中心人物特定"
        )
        main_focus = res_who.choices[0].message.content.strip().splitlines()[0]
    except Exception:
        logger.exception("[Mermaid] main focus extraction error")
        main_focus = "主人公"
    
    logger.info(f"[Q{q_num}] Main focus = {main_focus}")

    # ──────────────────────────
    # Step 2: 中心人物を基にざっくりMermaid図を生成
    # ──────────────────────────
    rough_mermaid_prompt = f"""
以下の質問と本文を基に、「{main_focus}」を中心とした主要登場人物の関係図をMermaid形式で生成してください。

質問: {question}

本文:
{story_text}

要件:
- graph LR または graph TD で開始
- **{main_focus}を中心**に、直接関わる主要人物のみを含める
- 登場人物は物語上重要な人物に限定する（5-10人程度）
- 関係性の表現：
  * 双方向の関係: <--> を使用（例: 友人、仲間、恋人など）
  * 一方向の関係: --> を使用（例: 上司→部下、師匠→弟子など）
  * 点線矢印 -.-> は補助的な関係に使用
- **重要**: 同じ2人の間の関係は最大2本まで（AからB、BからA）
- エッジには簡潔な日本語ラベルを付ける（5文字以内推奨）
- 必要に応じてsubgraphでグループ化（例: 勇者パーティー、魔王軍など）
- {main_focus}に直接関わらない人物間の関係は省略する

出力はMermaidコードのみ（説明不要）
"""
    
    try:
        res_rough = openai_chat(
            "gpt-4.1",  # 高速化のため
            messages=[
                {"role": "system", "content": "Mermaid図を生成する専門家です。"},
                {"role": "user", "content": rough_mermaid_prompt}
            ],
            temperature=0.3,
            log_label="Mermaid図ざっくり生成"
        )
        rough_mermaid = res_rough.choices[0].message.content.strip()
        # コードブロック記号を除去
        rough_mermaid = rough_mermaid.replace('```mermaid', '').replace('```', '').strip()
        logger.debug(f"[Q{q_num}] Rough Mermaid = {rough_mermaid[:500]}")
    except Exception:
        logger.exception("[Mermaid] Rough generation error")
        rough_mermaid = f"graph LR\n    {main_focus} --> 誰か"

    # ──────────────────────────
    # Step 3: Mermaid図をCSVに変換（検証のため）
    # ──────────────────────────
    csv_prompt = f"""
以下のMermaid図から人物関係を抽出してCSV形式で出力してください。
「{main_focus}」を中心とした主要人物の関係のみを抽出してください。

Mermaid図:
{rough_mermaid}

本文（参考）:
{story_text}

出力形式:
主体,関係タイプ,関係詳細,客体,グループ

説明:
- 主体: 関係の起点となる人物
- 関係タイプ: directed（一方向）, bidirectional（双方向）, dotted（点線）
- 関係詳細: 関係を表す日本語（5文字以内）
- 客体: 関係の終点となる人物
- グループ: subgraphに属する場合はグループ名、なければ空欄

重要な制約:
- **同じ2人の間の関係は最大2本まで**（A→B と B→A のみ）
- 同じ方向の重複する関係は1つにまとめる
- 本文に存在しない人物関係は除外
- {main_focus}に直接関わる人物を優先
- {main_focus}に直接関わらない人物間の関係は省略
- ヘッダーは不要
"""

    try:
        res_csv = openai_chat(
            "gpt-4.1",
            messages=[
                {"role": "system", "content": "Mermaid図と本文を照合して正確な関係を抽出します。"},
                {"role": "user", "content": csv_prompt}
            ],
            temperature=0,
            log_label="MermaidをCSVに変換"
        )
        csv_text = res_csv.choices[0].message.content.strip()
        logger.debug(f"[Q{q_num}] Validated CSV = {csv_text[:400]}")
    except Exception:
        logger.exception("[Mermaid] CSV conversion error")
        csv_text = f"{main_focus},directed,関係,誰か,"

    # ──────────────────────────
    # Step 4: CSVからルールベースでMermaid図を再構築
    # ──────────────────────────
    def build_mermaid_from_csv(csv_text: str, main_focus: str = None) -> str:
        """
        CSVデータから正確なMermaid図を構築
        重複する関係を統合し、同じペア間の関係を最大2本（双方向）に制限
        """
        # ノードとエッジの収集
        nodes = set()
        edges = []
        groups = {}  # グループ名 -> ノードリスト
        edge_map = {}  # (src, dst)のペアをキーにして重複チェック

        reader = csv.reader(csv_text.splitlines())
        for row in reader:
            if len(row) < 4:
                continue

            src = row[0].strip()
            rel_type = row[1].strip() if len(row) > 1 else "directed"
            rel_label = row[2].strip() if len(row) > 2 else "関係"
            dst = row[3].strip() if len(row) > 3 else ""
            group = row[4].strip() if len(row) > 4 else ""

            if not src or not dst:
                continue

            # 同じペア（順序あり）の重複チェック
            edge_key = (src, dst)
            if edge_key in edge_map:
                # 既に同じ方向の関係がある場合はスキップ
                continue

            nodes.add(src)
            nodes.add(dst)

            # グループの記録
            if group:
                if group not in groups:
                    groups[group] = set()
                groups[group].add(src)
                groups[group].add(dst)

            # エッジの記録
            edge_symbol = "-->"  # デフォルト
            if rel_type.lower() in ["bidirectional", "双方向"]:
                edge_symbol = "<-->"
            elif rel_type.lower() in ["dotted", "点線"]:
                edge_symbol = "-.->"

            edges.append({
                "src": src,
                "dst": dst,
                "symbol": edge_symbol,
                "label": rel_label[:5]  # 5文字制限に変更
            })
            edge_map[edge_key] = True
        
        # Mermaid図の構築
        lines = ["graph LR"]
        
        # ノードIDの生成（安全な識別子）
        def safe_id(name: str) -> str:
            # 日本語をそのまま使える場合
            return f'id_{abs(hash(name)) % 10000}'
        
        node_ids = {name: safe_id(name) for name in nodes}
        
        # ノード定義
        for name in sorted(nodes):
            node_id = node_ids[name]
            lines.append(f'    {node_id}["{name}"]')
        
        # サブグラフの定義
        if groups:
            for group_name, group_nodes in groups.items():
                safe_group_name = re.sub(r'[^0-9A-Za-z_\u3040-\u30FF\u4E00-\u9FFF\s]', '', group_name)
                lines.append(f'\n    subgraph {safe_group_name}')
                for node in group_nodes:
                    if node in node_ids:
                        lines.append(f'        {node_ids[node]}')
                lines.append('    end')
        
        # エッジの定義
        lines.append('')  # 空行
        for edge in edges:
            if edge["src"] in node_ids and edge["dst"] in node_ids:
                src_id = node_ids[edge["src"]]
                dst_id = node_ids[edge["dst"]]
                
                if edge["label"]:
                    if edge["symbol"] == "<-->":
                        lines.append(f'    {src_id} <-->|{edge["label"]}| {dst_id}')
                    elif edge["symbol"] == "-.->":
                        lines.append(f'    {src_id} -.->|{edge["label"]}| {dst_id}')
                    else:
                        lines.append(f'    {src_id} -->|{edge["label"]}| {dst_id}')
                else:
                    lines.append(f'    {src_id} {edge["symbol"]} {dst_id}')
        
        # 中心人物の強調
        if main_focus and main_focus in node_ids:
            lines.append(f'\n    style {node_ids[main_focus]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
        
        return '\n'.join(lines)

    # ──────────────────────────
    # Step 5: 最終的なMermaid図を生成
    # ──────────────────────────
    final_mermaid = build_mermaid_from_csv(csv_text, main_focus)
    logger.debug(f"[Q{q_num}] Final Mermaid = {final_mermaid[:500]}")

    # ──────────────────────────
    # Step 6: Kroki APIでSVG生成
    # ──────────────────────────
    mmd_path = Path(user_dir) / f"{st.session_state.user_name}_{st.session_state.user_number}_{q_num}.mmd"
    svg_path = mmd_path.with_suffix(".svg")

    # Mermaidファイルを保存
    mmd_path.write_text(final_mermaid, encoding="utf-8")

    # デバッグ用：生成されたMermaidコードも保存
    debug_path = Path(user_dir) / f"debug_mermaid_{q_num}.txt"
    debug_content = f"""=== ROUGH MERMAID ===
{rough_mermaid}

=== CSV DATA ===
{csv_text}

=== FINAL MERMAID ===
{final_mermaid}
"""
    debug_path.write_text(debug_content, encoding="utf-8")

    try:
        # Kroki APIを使用してSVG生成
        import base64
        import zlib
        import requests

        # MermaidコードをKroki形式でエンコード（zlib + base64）
        compressed = zlib.compress(final_mermaid.encode('utf-8'), 6)
        encoded = base64.urlsafe_b64encode(compressed).decode('utf-8')

        # Kroki APIのURL（SVG形式）
        api_url = f"https://kroki.io/mermaid/svg/{encoded}"

        # SVG画像をダウンロード
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        # SVGファイルとして保存
        svg_path.write_text(response.text, encoding="utf-8")
        logger.info(f"[Q{q_num}] SVG generated successfully via Kroki API")
        return str(svg_path)

    except Exception as e:
        logger.exception(f"[Q{q_num}] Mermaid SVG generation failed")
        st.warning("⚠️ Mermaid 図生成に失敗しました。生成されたコードを表示します。")
        st.code(final_mermaid, language="mermaid")
        st.error(f"エラー詳細: {str(e)}")
        return None

# =================================================
#                   レイアウト
# =================================================
left_col, right_col = st.columns([5, 4])

# -------------------------------------------------
# 左：小説表示と質問入力
# -------------------------------------------------
with left_col:
    st.markdown("### 📖 小説")
    real_page_index = START_PAGE + st.session_state.ui_page

    nav1, nav2, nav3 = st.columns([1, 3, 1])
    with nav1:
        if st.button("◀ 前へ", disabled=(st.session_state.ui_page == 0)):
            logger.info(f"Navigate prev -> UI page {st.session_state.ui_page-1}")
            st.session_state.ui_page -= 1
            st.rerun()
    with nav2:
        st.markdown(f"<center>ページ {real_page_index + 1} / {total_pages}</center>",
                    unsafe_allow_html=True)
    with nav3:
        if st.button("次へ ▶",
                     disabled=(st.session_state.ui_page >= total_ui_pages-1)):
            logger.info(f"Navigate next -> UI page {st.session_state.ui_page+1}")
            st.session_state.ui_page += 1
            st.rerun()

    st.session_state.page = real_page_index
    st.markdown(
        f"""
        <div style="
            padding:20px;border-radius:10px;background-color:#FFF8DC;
            font-size:18px;line-height:1.8;white-space:pre-wrap;
            min-height:500px;max-height:600px;overflow-y:auto;">
        {pages_all[real_page_index]}
        </div>
        """, unsafe_allow_html=True
    )

    st.markdown("### 💬 質問")
    user_input_text = st.text_area(
        "この小説について質問してください",
        height=100,
        key="question_input",
        placeholder="例: 主人公の名前は何ですか？"
    )
    send_button = st.button("📤 送信", type="primary", use_container_width=True)

    # ボタンが押されたときに user_input に値を設定
    user_input = None
    if send_button and user_input_text.strip():
        user_input = user_input_text.strip()

# -------------------------------------------------
# 右：履歴 & 図 & ログ DL
# -------------------------------------------------
with right_col:
    st.markdown("### 📝 質問・回答履歴")
    chat_box = st.container(height=600)

    with chat_box:
        if not st.session_state.chat_history:
            st.info("まだ質問がありません。左側の入力欄から質問してください。")
        else:
            for item in st.session_state.chat_history:
                if item["type"] == "question":
                    st.markdown(
                        f'<div style="background:#DCF8C6;padding:10px;border-radius:10px;margin:5px 0;">'
                        f'<b>質問:</b> {item["content"]}</div>',
                        unsafe_allow_html=True)
                elif item["type"] == "answer":
                    st.markdown(
                        f'<div style="background:#F1F0F0;padding:10px;border-radius:10px;margin:5px 0;">'
                        f'<b>回答:</b> {item["content"]}</div>',
                        unsafe_allow_html=True)
                elif item["type"] == "image" and Path(item["path"]).exists():
                    st.image(item["path"], caption=item["caption"],
                             use_container_width=True)

    # ログダウンロードボタン
    st.markdown("---")
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            log_content = f.read()

        st.download_button(
            label="📥 詳細ログをダウンロード",
            data=log_content,
            file_name=f"{st.session_state.user_name}_{st.session_state.user_number}_chat_log.txt",
            mime="text/plain",
            use_container_width=True
        )
    else:
        st.info("ログファイルがまだ作成されていません")

# =================================================
#               ユーザー入力処理
# =================================================
if user_input:
    st.session_state.question_number += 1
    q_num = st.session_state.question_number
    logger.info(f"[Q{q_num}] {user_input}")

    # 質問を履歴に追加
    st.session_state.chat_history.append(
        {"type": "question", "number": q_num, "content": user_input}
    )

    # 質問をすぐに表示
    st.markdown(
        f'<div style="background:#DCF8C6;padding:10px;border-radius:10px;margin:5px 0;">'
        f'<b>質問:</b> {user_input}</div>',
        unsafe_allow_html=True)

    story_text_so_far = "\n\n".join(pages_all[:real_page_index + 1])

    # 登場人物の関係図生成
    svg_file = None
    mermaid_code = None
    if is_character_question(user_input):
        status_placeholder = st.empty()
        status_placeholder.info("💭 登場人物の関係図を生成中...")
        svg_file = generate_mermaid_file(user_input, story_text_so_far, q_num)
        status_placeholder.empty()
        if svg_file:
            st.session_state.chat_history.append(
                {"type": "image",
                 "path": svg_file,
                 "caption": f"登場人物関係図 (質問 #{q_num})"})
            # SVG画像を表示
            st.image(svg_file, caption=f"登場人物関係図 (質問 #{q_num})", use_container_width=True)

            # Mermaidコードを読み込む
            mmd_path = Path(svg_file).with_suffix(".mmd")
            if mmd_path.exists():
                mermaid_code = mmd_path.read_text(encoding="utf-8")

    # 回答生成
    status_placeholder = st.empty()
    status_placeholder.info("💭 回答を生成中...")

    prompt = f"""
以下はユーザーがこれまでに読んだ小説本文です。

----- 本文ここから -----
{story_text_so_far}
----- 本文ここまで -----

# 指示
この本文の内容を根拠にユーザーの質問に日本語で丁寧に答えてください。
"""
    st.session_state.messages.append(
        {"role": "user", "content": prompt + "\n\n質問: " + user_input}
    )

    try:
        resp  = openai_chat(
                    "gpt-4.1",
                    messages=st.session_state.messages,
                    temperature=0.7,
                    log_label="質問への回答生成"
                )
        reply = resp.choices[0].message.content.strip()
        status_placeholder.empty()

        st.session_state.chat_history.append(
            {"type": "answer", "content": reply}
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": reply})
        logger.info(f"[A{q_num}] 回答生成完了")

        # Google SheetsにQAログを記録
        if sheets_qa_logger:
            sheets_qa_logger.log_qa(
                user_name=st.session_state.user_name,
                user_number=st.session_state.user_number,
                q_num=q_num,
                question=user_input,
                answer=reply,
                mermaid_code=mermaid_code,
                svg_path=svg_file
            )

    except Exception as e:
        status_placeholder.empty()
        err = f"エラーが発生しました: {e}"
        st.session_state.chat_history.append(
            {"type": "answer", "content": err}
        )
        st.error(err)
        logger.exception("回答生成失敗")

    st.rerun()
