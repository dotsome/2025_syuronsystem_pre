# ===============================================
#  実験用システム（改良版）
#          ── 2段階Mermaid生成システム ──
# ===============================================
import os, json, subprocess, logging, re, time, csv
from pathlib import Path
from functools import wraps
from logging.handlers import RotatingFileHandler
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Literal
from pydantic import BaseModel
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
# 実験モード設定
# -------------------------------------------------
# 実験ナンバーでモードを切り替える
# 0: デモモード（桃太郎、0章から）
# 1: モード1「X-1章までの情報を使い関係図や質問応答を行う，読者はX章以降を読む」
# 2: モード2「質問を送信するだけのモード（システムは応答も何も行わない）」
# 3: モード3「Y章までの情報を使い関係図や質問応答を行う，読者はX章以降を読む」
# 4: モード4「X-1章までの情報を使い質問応答を行う（関係図は生成しない），読者はX章以降を読む」
# 5: モード5「X-1章までの情報を使い関係図や質問応答を行う，関係図作成でmainの人物は特定せず全体の人物関係図を出力する，読者はX章以降を読む」

# 実験設定
X = 30  # 読者が読み始める章
Y = 40  # モード3で使用する最大章数

# モード別機能フラグを返す関数
def get_mode_config(experiment_mode: int):
    """実験モード番号から設定を取得"""
    MODE_CONFIG = {
        0: {"use_graph": True,  "use_qa": True,  "context_range": "all",    "graph_type": "main_character"},  # デモ
        1: {"use_graph": True,  "use_qa": True,  "context_range": X-1,      "graph_type": "main_character"},  # モード1
        2: {"use_graph": False, "use_qa": False, "context_range": 0,        "graph_type": None},              # モード2
        3: {"use_graph": True,  "use_qa": True,  "context_range": Y,        "graph_type": "main_character"},  # モード3
        4: {"use_graph": False, "use_qa": True,  "context_range": X-1,      "graph_type": None},              # モード4
        5: {"use_graph": True,  "use_qa": True,  "context_range": X-1,      "graph_type": "all_characters"},  # モード5
    }
    return MODE_CONFIG.get(experiment_mode, MODE_CONFIG[1])  # デフォルトはモード1

# -------------------------------------------------
# 小説選択
# -------------------------------------------------
NOVEL_FILE = "shadow_text.json"  # 使用する小説ファイル: "beast_text.json", "shadow_text.json", または "kabi_text.json"
# NOVEL_FILE = "kabi_text.json"  # 田山花袋「蒲団」(79章)

# =================================================
#                🔸  ロガー関連
# =================================================
class GoogleDriveUploader:
    """Google Driveにファイルをアップロードするクラス"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.service = None
            cls._instance.folder_id = None
            cls._instance._init_service()
        return cls._instance

    def _init_service(self):
        """Google Drive APIサービスを初期化（OAuth または サービスアカウント）"""
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            # OAuth認証を優先（個人ドライブへのアップロードが可能）
            if "google_drive_oauth" in st.secrets:
                from google.oauth2.credentials import Credentials

                oauth_config = dict(st.secrets["google_drive_oauth"])
                creds = Credentials(
                    token=oauth_config.get("token"),
                    refresh_token=oauth_config.get("refresh_token"),
                    token_uri=oauth_config.get("token_uri"),
                    client_id=oauth_config.get("client_id"),
                    client_secret=oauth_config.get("client_secret"),
                    scopes=oauth_config.get("scopes", ["https://www.googleapis.com/auth/drive.file"])
                )
                self.service = build('drive', 'v3', credentials=creds)
                self.folder_id = oauth_config.get("folder_id", None)
                print(f"✅ [INIT] Google Drive API接続成功 (OAuth認証, folder_id: {self.folder_id or 'ルート'})")

            # サービスアカウント認証（共有ドライブのみ）
            elif "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                scope = [
                    'https://www.googleapis.com/auth/drive.file',
                    'https://www.googleapis.com/auth/drive'
                ]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                self.service = build('drive', 'v3', credentials=creds)

                if "google_drive_folder_id" in st.secrets:
                    self.folder_id = st.secrets["google_drive_folder_id"]
                    print(f"✅ [INIT] Google Drive API接続成功 (サービスアカウント, folder_id: {self.folder_id})")
                else:
                    print(f"⚠️ [INIT] サービスアカウント認証成功だが、google_drive_folder_idが未設定")
                    print(f"   サービスアカウントは共有ドライブのみアップロード可能です")
            else:
                print("⚠️ [INIT] google_drive_oauth も gcp_service_account も見つかりません")

        except Exception as e:
            print(f"❌ [INIT] Google Drive API初期化エラー: {e}")
            import traceback
            traceback.print_exc()

    def upload_file(self, file_path: str, folder_id: str = None, max_retries: int = 3) -> str | None:
        """ファイルをGoogle Driveにアップロード（リトライ機能付き）"""
        print(f"🔍 [UPLOAD] upload_file()呼び出し: {file_path}")

        if self.service is None:
            print(f"⚠️ [UPLOAD] Google Drive service が初期化されていません")
            return None

        try:
            from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
            from googleapiclient.errors import ResumableUploadError
            import io

            file_path = Path(file_path)
            if not file_path.exists():
                print(f"⚠️ [UPLOAD] ファイルが存在しません: {file_path}")
                return None

            print(f"✅ [UPLOAD] ファイル確認OK: {file_path.name} ({file_path.stat().st_size} bytes)")

            # MIMEタイプの判定
            mime_types = {
                '.txt': 'text/plain',
                '.log': 'text/plain',
                '.svg': 'image/svg+xml',
                '.mmd': 'text/plain',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.json': 'application/json',
                '.pdf': 'application/pdf',
            }
            mime_type = mime_types.get(file_path.suffix, 'application/octet-stream')

            # アップロード先フォルダID（優先順位: 引数 > インスタンス変数）
            target_folder = folder_id or self.folder_id

            # ファイルメタデータ
            file_metadata = {'name': file_path.name}

            # フォルダIDがある場合のみparentsを設定
            if target_folder:
                file_metadata['parents'] = [target_folder]
                print(f"📁 [UPLOAD] アップロード先フォルダID: {target_folder}")
            else:
                print(f"📁 [UPLOAD] アップロード先: マイドライブのルート")

            # ファイルサイズを確認
            file_size = file_path.stat().st_size

            # 5MB以下の小さいファイルは非resumableアップロードを使用
            # resumableアップロードはネットワークの問題でエラーになりやすい
            if file_size < 5 * 1024 * 1024:  # 5MB
                # 小さいファイルは一括アップロード（resumable=False）
                with open(file_path, 'rb') as f:
                    media = MediaIoBaseUpload(
                        io.BytesIO(f.read()),
                        mimetype=mime_type,
                        resumable=False
                    )
                    file = self.service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id, webViewLink'
                    ).execute()
            else:
                # 大きいファイルはリトライ付きのresumableアップロード
                for attempt in range(max_retries):
                    try:
                        media = MediaFileUpload(
                            str(file_path),
                            mimetype=mime_type,
                            resumable=True,
                            chunksize=1024 * 1024  # 1MBチャンク
                        )
                        file = self.service.files().create(
                            body=file_metadata,
                            media_body=media,
                            fields='id, webViewLink'
                        ).execute()
                        break  # 成功したらループを抜ける
                    except ResumableUploadError as e:
                        if attempt < max_retries - 1:
                            print(f"アップロード失敗（リトライ {attempt + 1}/{max_retries}）: {e}")
                            time.sleep(2 ** attempt)  # 指数バックオフ
                        else:
                            raise  # 最後のリトライで失敗したら例外を投げる

            file_id = file.get('id')

            # ファイルを誰でも閲覧可能に設定
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            self.service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()

            # 画像直接表示用のURL（Google Drive direct link）
            direct_link = f"https://drive.google.com/uc?id={file_id}"

            print(f"✅ [UPLOAD] Google Driveにアップロード完了: {file_path.name} (ID: {file_id})")
            print(f"🔗 [UPLOAD] URL: {direct_link}")
            return direct_link

        except Exception as e:
            print(f"❌ [UPLOAD] Google Driveアップロードエラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_folder(self, folder_name: str, parent_folder_id: str = None) -> str | None:
        """Google Drive上にフォルダを作成"""
        if self.service is None:
            return None

        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            folder_id = folder.get('id')
            print(f"✅ Google Driveにフォルダ作成完了: {folder_name} (ID: {folder_id})")
            return folder_id

        except Exception as e:
            print(f"Google Driveフォルダ作成エラー: {e}")
            return None

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
               svg_path: str = None, drive_uploader=None,
               timestamp: str = None, chapter: str = None, chapter_title: str = None):
        """質問・回答・図をGoogle Sheetsに記録（レート制限対策付き）"""
        print(f"🔍 [DEBUG] log_qa() 呼び出し: Q{q_num}, svg_path={svg_path}, drive_uploader={'あり' if drive_uploader else 'なし'}")

        if self.spreadsheet is None:
            print(f"⚠️ [DEBUG] spreadsheet is None - log_qa()をスキップ")
            return

        try:
            # レート制限対策: 前回の書き込みから2秒待つ
            if hasattr(self, '_last_qa_write'):
                elapsed = time.time() - self._last_qa_write
                if elapsed < 2:
                    time.sleep(2 - elapsed)

            # SVGファイルの内容を読み込む
            svg_content = ""
            svg_drive_link = ""
            if svg_path and Path(svg_path).exists():
                try:
                    svg_content = Path(svg_path).read_text(encoding='utf-8')
                    print(f"🔍 [DEBUG] SVG読み込み成功: {len(svg_content)} 文字")

                    # SVGファイルをGoogle Driveにアップロード
                    if drive_uploader:
                        print(f"🔄 [Q{q_num}] Google Driveアップロード試行: {svg_path}")
                        svg_drive_link = drive_uploader.upload_file(svg_path) or ""

                        if svg_drive_link:
                            print(f"✅ [Q{q_num}] アップロード成功: {svg_drive_link}")
                        else:
                            print(f"⚠️ [Q{q_num}] アップロード失敗: リンクが返されませんでした")
                    else:
                        print(f"⚠️ [Q{q_num}] drive_uploaderがNoneです")

                except Exception as e:
                    print(f"❌ [Q{q_num}] SVG読み込み/アップロードエラー: {e}")
                    import traceback
                    traceback.print_exc()
                    svg_content = f"[SVG読み込み失敗: {svg_path}]"
            else:
                if not svg_path:
                    print(f"⚠️ [Q{q_num}] svg_pathがNoneです")
                elif not Path(svg_path).exists():
                    print(f"⚠️ [Q{q_num}] SVGファイルが存在しません: {svg_path}")

            # QA専用ワークシートを取得/作成（ユーザーごとに分ける）
            worksheet_name = f"QA_Logs_{user_number}"
            worksheet = self.get_or_create_worksheet(
                worksheet_name,
                headers=["Timestamp", "User", "Number", "Question#", "Chapter", "Chapter_Title",
                        "Question", "Answer", "Has_Diagram", "Mermaid_Code",
                        "SVG_Content", "SVG_Drive_Link"]
            )

            if worksheet:
                row_data = [
                    timestamp if timestamp else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    user_name,
                    user_number,
                    str(q_num),
                    chapter if chapter else "N/A",
                    chapter_title if chapter_title else "N/A",
                    question,
                    answer,
                    "Yes" if mermaid_code else "No",
                    mermaid_code if mermaid_code else "",
                    svg_content if svg_content else "",
                    svg_drive_link if svg_drive_link else ""
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
            # スレッドセーフ: ScriptRunContextが存在する場合のみアクセス
            try:
                record.user  = st.session_state.get("user_name", "-")
                record.q_num = st.session_state.get("question_number", 0)
            except Exception:
                # スレッド内など、Streamlitコンテキストがない場合はデフォルト値
                record.user  = "-"
                record.q_num = 0
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

    # 既存のハンドラーをすべてクリア（Streamlit再実行時の重複を防ぐ）
    logger.handlers.clear()

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
    特定の引数名（story_text等）は自動的に省略される
    """
    def _decorator(func):
        @wraps(func)
        def _wrapper(*args, **kwargs):
            t0 = time.time()
            logger = logging.getLogger("app")

            # 引数を省略形式に変換
            def sanitize_arg(arg):
                """長いテキストや特定のキーワードを含む引数を省略"""
                if isinstance(arg, str):
                    # 特定のキーワードで始まる長い文字列を省略
                    if len(arg) > 500 and any(keyword in arg[:200] for keyword in ['【', '章】', 'それは、', '魔王']):
                        return f"[本文省略: {len(arg)}文字]"
                    # 一般的な長い文字列も省略
                    elif len(arg) > 1000:
                        return f"[長文省略: {len(arg)}文字]"
                return arg

            # argsを処理
            sanitized_args = tuple(sanitize_arg(arg) for arg in args)

            # kwargsを処理（特定の引数名をチェック）
            sanitized_kwargs = {}
            for key, value in kwargs.items():
                if key in ['story_text', 'story_text_so_far', 'text'] and isinstance(value, str) and len(value) > 500:
                    sanitized_kwargs[key] = f"[本文省略: {len(value)}文字]"
                else:
                    sanitized_kwargs[key] = sanitize_arg(value)

            logger.debug(f"[IN ] {func.__name__} args={sanitized_args} kwargs={sanitized_kwargs}")

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
# OpenAI 呼び出しラッパ（処理時間計測付き + リトライ機能）
# -------------------------------------------------
def openai_chat(model: str, messages: list[dict], log_label: str = None, max_retries: int = 3, **kw):
    """
    OpenAI APIを呼び出し、処理時間を計測してログに記録
    500エラー時は自動リトライ（指数バックオフ）

    Args:
        model: 使用するモデル名
        messages: メッセージリスト
        log_label: ログに記録するラベル（例: "質問判定", "中心人物特定"）
        max_retries: 最大リトライ回数（デフォルト: 3）
        **kw: その他のパラメータ
    """
    logger = logging.getLogger("app")

    # プロンプトの長さを計算
    total_chars = sum(len(str(msg.get('content', ''))) for msg in messages)

    for attempt in range(max_retries):
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

            # リトライした場合は成功を明記
            if attempt > 0:
                log_msg += f" (リトライ{attempt}回目で成功)"

            logger.info(log_msg)

            return response

        except openai.InternalServerError as e:
            # 500エラー: サーバー側のエラー
            elapsed = time.time() - start_time

            if attempt < max_retries - 1:
                # まだリトライ可能
                wait_time = 2 ** attempt  # 指数バックオフ: 1秒, 2秒, 4秒...
                logger.warning(
                    f"⚠️ LLM呼び出し一時エラー [{log_label}]: model={model}, time={elapsed:.2f}s, "
                    f"error={str(e)}, リトライ{attempt + 1}/{max_retries} ({wait_time}秒後)"
                )
                time.sleep(wait_time)
            else:
                # 最後のリトライも失敗
                logger.error(
                    f"❌ LLM呼び出し失敗（{max_retries}回リトライ後） [{log_label}]: "
                    f"model={model}, time={elapsed:.2f}s, error={str(e)}"
                )
                raise

        except openai.RateLimitError as e:
            # レート制限エラー
            elapsed = time.time() - start_time

            if attempt < max_retries - 1:
                wait_time = 5 * (2 ** attempt)  # レート制限は長めに待つ: 5秒, 10秒, 20秒...
                logger.warning(
                    f"⚠️ レート制限エラー [{log_label}]: model={model}, time={elapsed:.2f}s, "
                    f"リトライ{attempt + 1}/{max_retries} ({wait_time}秒後)"
                )
                time.sleep(wait_time)
            else:
                logger.error(f"❌ レート制限エラー（{max_retries}回リトライ後） [{log_label}]: model={model}, time={elapsed:.2f}s")
                raise

        except Exception as e:
            # その他のエラー（リトライしない）
            elapsed = time.time() - start_time
            logger.error(f"❌ LLM呼び出し失敗 [{log_label}]: model={model}, time={elapsed:.2f}s, error={str(e)}")
            raise

# =================================================
#           Pydantic スキーマ定義
# =================================================

class Relationship(BaseModel):
    """登場人物間の関係"""
    source: str  # 関係の起点となる人物
    target: str  # 関係の終点となる人物
    relation_type: Literal["directed", "bidirectional", "dotted"]  # 関係のタイプ
    label: str  # 関係の詳細（5文字以内推奨）
    group: str = ""  # subgraphグループ名（オプション）

class CharacterGraph(BaseModel):
    """登場人物関係図の構造化データ"""
    center_person: str  # 中心人物
    relationships: List[Relationship]  # 関係のリスト

# 無効なノード名のセット
INVALID_NODES = {
    '不明', '主体', '客体', 'グループ', '関係タイプ', '関係詳細',
    '?', '？', 'None', 'none', 'null', 'NULL', ''
}

def build_mermaid_from_structured(graph: CharacterGraph) -> str:
    """
    Structured OutputsのCharacterGraphからMermaid図を構築

    従来のCSV処理で行っていた工夫をルールベースで適用:
    - 重複エッジの排除（同じペア・同じ方向は1つまで）
    - ラベル文字数制限（5文字以内）
    - ノードのソート（一貫性）
    - グループ名のサニタイズ

    Args:
        graph: CharacterGraphオブジェクト

    Returns:
        Mermaid図のコード
    """
    lines = ["graph LR"]

    # ノードとエッジを収集（重複排除付き）
    nodes = set()
    edges = []
    groups = {}
    edge_map = {}  # (src, dst)のペアをキーにして重複チェック

    # デバッグ用: フィルタされた関係を記録
    filtered_count = {"invalid": 0, "empty": 0, "duplicate": 0}

    for rel in graph.relationships:
        # INVALIDチェック
        if rel.source in INVALID_NODES or rel.target in INVALID_NODES:
            filtered_count["invalid"] += 1
            logger.debug(f"[Mermaid] Filtered INVALID node: {rel.source} -> {rel.target}")
            continue

        # 空文字列・None・空白のみのチェック
        if not rel.source or not rel.target or not rel.source.strip() or not rel.target.strip():
            filtered_count["empty"] += 1
            logger.warning(f"[Mermaid] Filtered EMPTY/WHITESPACE: source='{rel.source}', target='{rel.target}', label='{rel.label}'")
            continue

        # 同じペア（順序あり）の重複チェック
        edge_key = (rel.source, rel.target)
        if edge_key in edge_map:
            filtered_count["duplicate"] += 1
            # 既に同じ方向の関係がある場合はスキップ
            continue

        # ノード登録
        nodes.add(rel.source)
        nodes.add(rel.target)

        # グループ情報
        if rel.group:
            if rel.group not in groups:
                groups[rel.group] = set()
            groups[rel.group].add(rel.source)
            groups[rel.group].add(rel.target)

        # エッジ記録（ラベルは5文字制限）
        edge_symbol = "-->"  # デフォルト
        if rel.relation_type == "bidirectional":
            edge_symbol = "<-->"
        elif rel.relation_type == "dotted":
            edge_symbol = "-.->"

        edges.append({
            "src": rel.source,
            "dst": rel.target,
            "symbol": edge_symbol,
            "label": rel.label[:5]  # 5文字制限
        })
        edge_map[edge_key] = True

    # フィルタリング統計をログ出力
    logger.info(f"[Mermaid] Filtering stats - Invalid: {filtered_count['invalid']}, Empty: {filtered_count['empty']}, Duplicate: {filtered_count['duplicate']}, Valid: {len(edges)}")

    # ノードIDの生成（安全な識別子）
    def safe_id(name: str) -> str:
        return f'id_{abs(hash(name)) % 10000}'

    node_ids = {name: safe_id(name) for name in nodes}

    # ノード定義（ソート済み）
    for name in sorted(nodes):
        node_id = node_ids[name]
        lines.append(f'    {node_id}["{name}"]')

    # グループ定義（グループ名をサニタイズ）
    if groups:
        lines.append('')
        for group_name, group_nodes in groups.items():
            # 中黒を除去（Kroki APIのエンコーディングで問題を引き起こすため）
            safe_group_name = group_name.replace('・', '')
            # その他の特殊文字を除去してサニタイズ
            safe_group_name = re.sub(r'[^0-9A-Za-z_\u3040-\u309F\u30A0-\u30FE\u4E00-\u9FFF\s]', '', safe_group_name)
            # 空白のみになった場合はデフォルト名
            if not safe_group_name.strip():
                safe_group_name = 'group'
            lines.append(f'    subgraph {safe_group_name}')
            for node in sorted(group_nodes):
                if node in node_ids:
                    lines.append(f'        {node_ids[node]}')
            lines.append('    end')

    # エッジ定義
    lines.append('')
    for edge in edges:
        # srcとdstが存在し、空でないことを確認
        if not edge.get("src") or not edge.get("dst"):
            continue
        if edge["src"] not in node_ids or edge["dst"] not in node_ids:
            continue

        src_id = node_ids[edge["src"]]
        dst_id = node_ids[edge["dst"]]

        # ノードIDが有効かチェック
        if not src_id or not dst_id:
            continue

        if edge.get("label"):
            if edge["symbol"] == "<-->":
                lines.append(f'    {src_id} <-->|{edge["label"]}| {dst_id}')
            elif edge["symbol"] == "-.->":
                lines.append(f'    {src_id} -.->|{edge["label"]}| {dst_id}')
            else:
                lines.append(f'    {src_id} -->|{edge["label"]}| {dst_id}')
        else:
            lines.append(f'    {src_id} {edge["symbol"]} {dst_id}')

    # 中心人物ハイライト（fuzzy matching）
    if graph.center_person:
        lines.append('')  # スタイル定義前に空行
        if graph.center_person in node_ids:
            lines.append(f'    style {node_ids[graph.center_person]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
        else:
            # 部分一致で検索
            for node_name in node_ids:
                if graph.center_person in node_name or node_name in graph.center_person:
                    lines.append(f'    style {node_ids[node_name]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
                    break  # 最初にマッチしたノードのみをハイライト

    # Noneを除外し、末尾の空行を削除
    filtered_lines = [line for line in lines if line is not None]
    # 末尾の連続する空行を削除
    while filtered_lines and filtered_lines[-1] == '':
        filtered_lines.pop()
    return '\n'.join(filtered_lines)

def build_mermaid_without_subgraph(graph: CharacterGraph) -> str:
    """
    subgraphなしでMermaid図を構築（タイムアウト対策）

    Args:
        graph: CharacterGraphオブジェクト

    Returns:
        Mermaid図のコード（subgraphなし）
    """
    lines = ["graph LR"]

    # ノードとエッジを収集
    nodes = set()
    edges = []
    edge_map = {}

    for rel in graph.relationships:
        # INVALIDチェック
        if rel.source in INVALID_NODES or rel.target in INVALID_NODES:
            continue

        # 空文字列チェック
        if not rel.source or not rel.target or not rel.source.strip() or not rel.target.strip():
            continue

        # 重複チェック
        edge_key = (rel.source, rel.target)
        if edge_key in edge_map:
            continue

        nodes.add(rel.source)
        nodes.add(rel.target)

        # エッジ記録
        edge_symbol = "-->"
        if rel.relation_type == "bidirectional":
            edge_symbol = "<-->"
        elif rel.relation_type == "dotted":
            edge_symbol = "-.->"

        edges.append({
            "src": rel.source,
            "dst": rel.target,
            "symbol": edge_symbol,
            "label": rel.label[:5]
        })
        edge_map[edge_key] = True

    # ノードIDの生成
    def safe_id(name: str) -> str:
        return f'id_{abs(hash(name)) % 10000}'

    node_ids = {name: safe_id(name) for name in nodes}

    # ノード定義
    for name in sorted(nodes):
        node_id = node_ids[name]
        lines.append(f'    {node_id}["{name}"]')

    # エッジ定義（subgraphはスキップ）
    lines.append('')
    for edge in edges:
        if not edge.get("src") or not edge.get("dst"):
            continue
        if edge["src"] not in node_ids or edge["dst"] not in node_ids:
            continue

        src_id = node_ids[edge["src"]]
        dst_id = node_ids[edge["dst"]]

        if not src_id or not dst_id:
            continue

        if edge.get("label"):
            if edge["symbol"] == "<-->":
                lines.append(f'    {src_id} <-->|{edge["label"]}| {dst_id}')
            elif edge["symbol"] == "-.->":
                lines.append(f'    {src_id} -.->|{edge["label"]}| {dst_id}')
            else:
                lines.append(f'    {src_id} -->|{edge["label"]}| {dst_id}')
        else:
            lines.append(f'    {src_id} {edge["symbol"]} {dst_id}')

    # 中心人物ハイライト
    if graph.center_person:
        lines.append('')
        if graph.center_person in node_ids:
            lines.append(f'    style {node_ids[graph.center_person]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
        else:
            for node_name in node_ids:
                if graph.center_person in node_name or node_name in graph.center_person:
                    lines.append(f'    style {node_ids[node_name]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
                    break

    # 末尾の空行を削除
    filtered_lines = [line for line in lines if line is not None]
    while filtered_lines and filtered_lines[-1] == '':
        filtered_lines.pop()
    return '\n'.join(filtered_lines)

# =================================================
#           Streamlit セッション初期化
# =================================================
def init_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

init_state("user_name",        "")
init_state("user_number",      "")
init_state("session_timestamp", "")  # セッション開始時刻（ユニーク化用）
init_state("profile_completed", False)  # プロファイル入力完了フラグ
init_state("summary_read",      False)  # 要約テキスト読了フラグ
init_state("question_number",  0)
init_state("ui_page",          0)   # UI 上でのページ（0 … START_PAGE）
# messages は毎回リセットするため、セッション状態では管理しない
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
                                              placeholder="0~5の数字を入力してください（実験モード指定）",
                                              help="0~5の数字で実験モードを指定します（0:デモモード、1~5:実験モード）")
            submitted = st.form_submit_button("次へ")

            if submitted:
                if nickname and experiment_number:
                    # 実験ナンバーが0~5の数字かチェック
                    if experiment_number.isdigit() and 0 <= int(experiment_number) <= 5:
                        # セッション開始時刻を生成（ユニークなディレクトリ作成用）
                        session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                        st.session_state.user_name = nickname
                        st.session_state.user_number = experiment_number
                        st.session_state.session_timestamp = session_timestamp
                        st.session_state.profile_completed = True
                        st.success("プロファイル設定完了!")
                        st.rerun()
                    else:
                        st.error("実験ナンバーは0~5の数字を入力してください")
                else:
                    st.error("ニックネームと実験ナンバーの両方を入力してください")

        # プロファイル入力画面ではここで停止
        st.stop()

    # プロファイル入力は完了したが、要約テキストをまだ読んでいない場合
    if not st.session_state.summary_read:
        st.title("📚 物語の要約")
        st.markdown("### システムを使用する前に、以下の要約をお読みください")

        # デモモードかどうかで表示テキストを切り替え
        if int(st.session_state.user_number) == 0:
            summary_text = "これはデモモードです。本番はここに要約する文章を表示します。"
        else:
            summary_text = """主人公シドは幼い頃から「陰の実力者」に憧れ、現代日本で格闘技や怪しい修行に明け暮れるが、トラックに轢かれてあっさり死亡し、魔力のある異世界の貴族カゲノー家に転生する。今度こそ陰の実力者になるべく、表では凡庸なモブ少年を演じつつ、裏で魔力と剣技を極限まで鍛え、スライム製ボディスーツや変形剣を開発して盗賊団を虐殺、資金と実験材料を集める。その過程で肉塊となっていた金髪エルフ少女アルファを救い、でっち上げの「ディアボロス教団」と「魔人ディアボロスの呪い」の神話を語って組織シャドウガーデンを設立、アルファやベータ、ガンマら元悪魔憑き達が本気でそれを信じて世界規模の秘密結社に育ててしまう。数年後、シドの姉クレアが教団に攫われる事件が起き、シャドウとなった彼はアルファ達と共に地下施設を急襲、覚醒薬で怪物化したオルバ子爵を圧倒的な技量と奥義「アイ・アム・アトミック」で消し飛ばす。その後シドは王都の魔剣士学園に入り、ツンデレ王女アレクシアに罰ゲーム告白からまさかの交際を申し込まれ、婚約者候補のゼノンとの駆け引きに巻き込まれる。やがてアレクシア誘拐事件が再び発生し、教団の実験施設、化物化した被験者、ゼノンのラウンズ入りの野望などが交錯、アルファやアイリス王女もそれぞれ別戦場で怪物と激突する中、シャドウが放った「アトミック」によってアジトごとゼノンは蒸発する。表向きはアーティファクト暴走として処理され、シドとアレクシアは関係を解消。裏ではガンマがシドの前世知識をもとにミツゴシ商会を巨大企業へ育て、チョコレートや化粧品で資金と影響力を拡大しつつ、教団のチルドレンやシャドウを騙る黒装束の偽者をニューらが拷問して始末する。一方で学術学園では天才研究者シェリーと義父ルスランが教団由来のアーティファクト解析に乗り出し、アイリスとアレクシアは紅の騎士団を軸に教団とシャドウガーデン、どちらが真の敵なのか探り始める。"""

        st.markdown(
            f"""
            <div style="
                padding:20px;border-radius:10px;
                background-color:var(--background-color);
                color:var(--text-color);
                border:1px solid var(--secondary-background-color);
                font-size:16px;line-height:1.8;white-space:pre-wrap;
                max-height:500px;overflow-y:auto;">
            {summary_text}
            </div>
            """, unsafe_allow_html=True
        )

        st.markdown("---")

        # カウントダウンタイマーの説明とタイマー表示
        st.markdown("""
        <div style="
            padding:20px;border-radius:10px;
            background-color:#4A5568;
            color:white;
            border:1px solid #2D3748;
            font-size:16px;line-height:1.8;">
        上記文章を5分間、心の中で音読してください。声に出しても構いません。
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # タイマーのセッション状態初期化
        if 'timer_running' not in st.session_state:
            st.session_state.timer_running = False
        if 'timer_seconds' not in st.session_state:
            st.session_state.timer_seconds = 300  # 5分 = 300秒

        # タイマー表示
        minutes = st.session_state.timer_seconds // 60
        seconds = st.session_state.timer_seconds % 60

        col_timer1, col_timer2, col_timer3 = st.columns([1, 2, 1])
        with col_timer2:
            st.markdown(f"""
            <div style="
                text-align:center;
                font-size:48px;
                font-weight:bold;
                padding:20px;
                background-color:#2D3748;
                color:white;
                border-radius:10px;
                border:2px solid #4A5568;">
            {minutes:02d}:{seconds:02d}
            </div>
            """, unsafe_allow_html=True)

        # スタート・ストップ・リセットボタン
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn1:
            if not st.session_state.timer_running:
                if st.button("⏱️ タイマー開始", key="timer_start", use_container_width=True):
                    st.session_state.timer_running = True
                    st.rerun()
            else:
                if st.button("⏸️ タイマー停止", key="timer_stop", use_container_width=True):
                    st.session_state.timer_running = False
                    st.rerun()

        with col_btn2:
            if st.button("🔄 リセット", key="timer_reset", use_container_width=True):
                st.session_state.timer_running = False
                st.session_state.timer_seconds = 300
                st.rerun()

        # タイマーが実行中の場合、1秒ごとにカウントダウン
        if st.session_state.timer_running:
            if st.session_state.timer_seconds > 0:
                import time
                time.sleep(1)
                st.session_state.timer_seconds -= 1
                st.rerun()
            else:
                st.session_state.timer_running = False
                st.success("✅ 5分間の音読が完了しました！")

        st.markdown("---")

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("次へ", key="summary_next", use_container_width=True):
                st.session_state.summary_read = True
                st.rerun()

        # 要約テキスト画面ではここで停止
        st.stop()

    # =================================================
    #          🔸 実験モード設定（ユーザー入力後）
    # =================================================
    # ユーザーが入力した実験ナンバーから実験モードを取得
    EXPERIMENT_MODE = int(st.session_state.user_number)
    CURRENT_MODE = get_mode_config(EXPERIMENT_MODE)
    DEMO_MODE = (EXPERIMENT_MODE == 0)
    START_PAGE = 0 if DEMO_MODE else X

    # デバッグ用：実験モード情報をサイドバーに表示（開発時のみ）
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🔧 実験モード情報")
        st.markdown(f"**実験ナンバー:** {EXPERIMENT_MODE}")
        st.markdown(f"**グラフ生成:** {'✅' if CURRENT_MODE['use_graph'] else '❌'}")
        st.markdown(f"**Q&A実行:** {'✅' if CURRENT_MODE['use_qa'] else '❌'}")
        st.markdown(f"**コンテキスト範囲:** {CURRENT_MODE['context_range']}")
        st.markdown(f"**グラフタイプ:** {CURRENT_MODE['graph_type']}")
        st.markdown(f"**開始ページ:** {START_PAGE}")
        st.markdown("---")

    # =================================================
    #          🔸 ユーザー別ディレクトリ & ログ
    # =================================================
    # zikken_result ディレクトリの作成
    base_dir = Path("zikken_result")
    base_dir.mkdir(exist_ok=True)

    # ユーザー別ディレクトリを zikken_result 配下に作成（タイムスタンプ付きでユニーク化）
    user_dir = base_dir / f"zikken_{st.session_state.user_name}_{st.session_state.user_number}_{st.session_state.session_timestamp}"
    user_dir.mkdir(exist_ok=True)

    log_file = user_dir / f"{st.session_state.user_name}_{st.session_state.user_number}_{st.session_state.session_timestamp}_chat_log.txt"
    logger   = _build_logger(log_file)
    logger.info("--- Session started ---")
    logger.info(f"実験モード: {EXPERIMENT_MODE}")
    logger.info(f"モード設定: use_graph={CURRENT_MODE['use_graph']}, use_qa={CURRENT_MODE['use_qa']}, context_range={CURRENT_MODE['context_range']}, graph_type={CURRENT_MODE['graph_type']}")
    logger.info(f"開始ページ: {START_PAGE} (X={X}, Y={Y})")

    # Google Sheets QAロガーの初期化（Streamlit Cloudで有効）
    sheets_qa_logger = None
    if "google_spreadsheet_key" in st.secrets:
        sheets_qa_logger = GoogleSheetsLogger(st.secrets["google_spreadsheet_key"])
        logger.info("✅ Google Sheets Logger 初期化完了")
    else:
        logger.warning("⚠️ google_spreadsheet_key が設定されていません")

    # Google Driveアップローダーの初期化（Streamlit Cloudで有効）
    drive_uploader = None
    if "gcp_service_account" in st.secrets:
        drive_uploader = GoogleDriveUploader()
        logger.info(f"✅ Google Drive Uploader 初期化完了 (folder_id: {drive_uploader.folder_id if drive_uploader.folder_id else 'None'})")
    else:
        logger.warning("⚠️ gcp_service_account が設定されていません")

    # =================================================
    #          OpenAI クライアント初期化
    # =================================================
    load_dotenv()

    # 環境変数またはStreamlit Secretsから取得
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]

    if not api_key:
        st.error("OPENAI_API_KEY が設定されていません。")
        st.stop()

    client = openai.OpenAI(api_key=api_key)

    st.title("📖 人物関係想起システム")

    # =================================================
    #              小説データ読み込み
    # =================================================
    @st.cache_data
    def load_story(demo_mode: bool):
        if demo_mode:
            # デモ用のテストデータ（桃太郎）
            return [
                {"section": "1", "title": "桃太郎の誕生",
                 "text": "昔々、あるところにおじいさんとおばあさんが住んでいました。\n\nある日、おばあさんが川で洗濯をしていると、大きな桃が流れてきました。おばあさんは桃を家に持ち帰り、おじいさんと一緒に桃を割ってみると、中から元気な男の子が生まれました。\n\n二人は大喜びで、この子を「桃太郎」と名付けて育てることにしました。"},
                {"section": "2", "title": "仲間との出会い",
                 "text": "桃太郎は立派な若者に成長しました。\n\nある日、桃太郎は鬼ヶ島へ鬼退治に行くことを決意しました。おばあさんが作ったきびだんごを持って旅に出た桃太郎は、途中で犬、猿、キジと出会いました。\n\n桃太郎がきびだんごを分け与えると、三匹は桃太郎のお供となり、一緒に鬼ヶ島へ向かうことになりました。"},
                {"section": "3", "title": "鬼退治",
                 "text": "桃太郎と仲間たちは鬼ヶ島に到着しました。\n\n鬼の大将は強く恐ろしい存在でしたが、桃太郎、犬、猿、キジは力を合わせて戦いました。犬は鬼に噛みつき、猿は引っ掻き、キジは目を突き、桃太郎は刀で戦いました。\n\n激しい戦いの末、桃太郎たちは鬼を退治し、鬼が盗んだ宝物を取り戻しました。桃太郎は宝物を持って村に帰り、おじいさんとおばあさんと幸せに暮らしました。"}
            ]
        else:
            # 本番用のデータ（NOVEL_FILEで指定された小説を読み込み）
            try:
                with open(NOVEL_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                st.error(f"⚠️ 小説ファイル '{NOVEL_FILE}' が見つかりません")
                return []

    @st.cache_data
    def prepare_pages(demo_mode: bool, start_page: int):
        """ページデータを準備（キャッシュ）"""
        story_sections = load_story(demo_mode)
        # story_sectionsをそのまま返す（辞書形式）
        pages_all = story_sections
        pages_ui_formatted = [f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
                              for sec in story_sections[start_page:]]
        return pages_all, pages_ui_formatted, len(pages_ui_formatted), len(pages_all)

    pages_all, pages_ui, total_ui_pages, total_pages = prepare_pages(DEMO_MODE, START_PAGE)

    # =================================================
    #  プロンプトキャッシュのウォームアップ（初回のみ）
    # =================================================
    def warmup_prompt_cache():
        """
        セッション開始時にダミー質問でプロンプトキャッシュを作成

        ウォームアップ内容:
        1. 本文キャッシュ（START_PAGEまで）
        2. 登場人物情報キャッシュ（character_summary.txt）

        これにより、ユーザーの最初の質問から高速な応答が可能になる
        """
        if "cache_warmed_up" not in st.session_state:
            st.session_state.cache_warmed_up = False

        if not st.session_state.cache_warmed_up:
            with st.spinner("🔥 システムを準備中...（初回のみ、数秒お待ちください）"):
                try:
                    # 1. START_PAGEまでの本文でキャッシュを作成
                    warmup_story_text = "\n\n".join([
                        f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
                        for sec in pages_all[:START_PAGE + 1]
                    ])

                    # ダミー質問でMermaid図生成プロンプトを実行（本文キャッシュ作成）
                    warmup_summary = """主人公シドは幼い頃から「陰の実力者」に憧れ、現代日本で格闘技や怪しい修行に明け暮れるが、トラックに轢かれてあっさり死亡し、魔力のある異世界の貴族カゲノー家に転生する。今度こそ陰の実力者になるべく、表では凡庸なモブ少年を演じつつ、裏で魔力と剣技を極限まで鍛え、スライム製ボディスーツや変形剣を開発して盗賊団を虐殺、資金と実験材料を集める。その過程で肉塊となっていた金髪エルフ少女アルファを救い、でっち上げの「ディアボロス教団」と「魔人ディアボロスの呪い」の神話を語って組織シャドウガーデンを設立、アルファやベータ、ガンマら元悪魔憑き達が本気でそれを信じて世界規模の秘密結社に育ててしまう。数年後、シドの姉クレアが教団に攫われる事件が起き、シャドウとなった彼はアルファ達と共に地下施設を急襲、覚醒薬で怪物化したオルバ子爵を圧倒的な技量と奥義「アイ・アム・アトミック」で消し飛ばす。その後シドは王都の魔剣士学園に入り、ツンデレ王女アレクシアに罰ゲーム告白からまさかの交際を申し込まれ、婚約者候補のゼノンとの駆け引きに巻き込まれる。やがてアレクシア誘拐事件が再び発生し、教団の実験施設、化物化した被験者、ゼノンのラウンズ入りの野望などが交錯、アルファやアイリス王女もそれぞれ別戦場で怪物と激突する中、シャドウが放った「アトミック」によってアジトごとゼノンは蒸発する。表向きはアーティファクト暴走として処理され、シドとアレクシアは関係を解消。裏ではガンマがシドの前世知識をもとにミツゴシ商会を巨大企業へ育て、チョコレートや化粧品で資金と影響力を拡大しつつ、教団のチルドレンやシャドウを騙る黒装束の偽者をニューらが拷問して始末する。一方で学術学園では天才研究者シェリーと義父ルスランが教団由来のアーティファクト解析に乗り出し、アイリスとアレクシアは紅の騎士団を軸に教団とシャドウガーデン、どちらが真の敵なのか探り始める。"""

                    warmup_prompt_story = f"""
    仮の要約テキスト:
    {warmup_summary}

    本文:
    {warmup_story_text}

    質問: 主人公について教えてください

    要件:
    - graph LR または graph TD で開始
    - **主人公を中心**に、直接関わる主要人物のみを含める
    - 登場人物は物語上重要な人物に限定する（5-10人程度）
    - 関係性の表現：
      * 双方向の関係: <--> を使用（例: 友人、仲間、恋人など）
      * 一方向の関係: --> を使用（例: 上司→部下、師匠→弟子など）
      * 点線矢印 -.-> は補助的な関係に使用
    - **重要**: 同じ2人の間の関係は最大2本まで（AからB、BからA）
    - エッジには簡潔な日本語ラベルを付ける（5文字以内推奨）
    - 必要に応じてsubgraphでグループ化（例: 勇者パーティー、魔王軍など）
    - 主人公に直接関わらない人物間の関係は省略する

    以上の質問と本文を基に、「主人公」を中心とした主要登場人物の関係図をMermaid形式で生成してください。
    出力はMermaidコードのみ（説明不要）
    """

                    # Structured Outputs用ウォームアップ（gpt-4o）
                    # 実際のMermaid生成と完全に同じプロンプト形式でキャッシュ作成
                    warmup_main_focus = "主人公"  # ダミーの中心人物
                    warmup_structured_prompt = f"""
仮の要約テキスト:
{warmup_summary}

本文:
{warmup_story_text}

質問: 主人公について教えてください
中心人物: {warmup_main_focus}

タスク: 本文を読み、{warmup_main_focus}を中心とした登場人物の関係図を構造化データで出力してください。

【重要な注意事項】
❌ 絶対にやってはいけないこと:
- 「不明」「質問者」「主体」「客体」などの抽象的な人物名は使用禁止
- 実在しない人物を含めない

✅ 正しい例:
- center_person: "ミナ"
- relationships: [
    {{"source": "ミナ", "target": "アリオス", "relation_type": "bidirectional", "label": "仲間", "group": "勇者パーティー"}},
    {{"source": "ミナ", "target": "レイン", "relation_type": "bidirectional", "label": "元仲間", "group": ""}}
  ]

要件:
1. {warmup_main_focus}を必ず含める
2. 実在する登場人物のみ（具体的な人物名）
3. 主要な関係のみ（5-10人程度）
4. 関係タイプ:
   - directed: 一方向（上司→部下など）
   - bidirectional: 双方向（友人、仲間など）
   - dotted: 補助的な関係
5. labelは簡潔に（5文字以内推奨）
6. 同じ2人の間の関係は最大2本まで

**絶対に守ること:**
- 「不明」「主体」「客体」などの抽象的な名前は絶対に使用しない
- 必ず実在する登場人物のみを使用する
- {warmup_main_focus}自身を必ず含める
"""

                    # Structured Outputs APIでキャッシュ作成
                    try:
                        _ = client.beta.chat.completions.parse(
                            model="gpt-5.1",
                            messages=[
                                {"role": "system", "content": "登場人物の関係図を構造化データで出力します。"},
                                {"role": "user", "content": warmup_structured_prompt}
                            ],
                            response_format=CharacterGraph,
                            temperature=0.3
                        )
                        logger.info("✅ Structured Outputs (gpt-5.1) キャッシュ作成完了")
                    except Exception as e:
                        logger.warning(f"⚠️ Structured Outputsキャッシュ作成失敗（続行します）: {e}")

                    # 回答生成用キャッシュ（gpt-5.1）
                    _ = openai_chat(
                        "gpt-5.1",
                        messages=[
                            {"role": "system", "content": "質問に回答するアシスタントです。"},
                            {"role": "user", "content": warmup_prompt_story}
                        ],
                        temperature=0.7,
                        log_label="キャッシュウォームアップ（回答・gpt-5.1）"
                    )

                    # 2. 登場人物情報でキャッシュを作成
                    # character_summary.txtを読み込み（この時点でセッションキャッシュにも保存される）
                    try:
                        summary_file = "character_summary_DEMO.txt" if DEMO_MODE else "character_summary.txt"
                        summary_path = Path(summary_file)
                        if summary_path.exists():
                            character_summary = summary_path.read_text(encoding="utf-8")
                            st.session_state.character_summary_cache = character_summary

                            # 登場人物情報キャッシュ作成
                            warmup_prompt_character = f"""
登場人物情報:
{character_summary}

---

質問: 主人公について教えてください

この質問の中心となる登場人物の名前を1つだけ答えてください。

要件:
- 登場人物情報に記載されている正確な人物名で回答
- 人物名のみを1行で出力（説明不要）

回答:
"""

                            _ = openai_chat(
                                "gpt-5.1",
                                messages=[
                                    {"role": "system", "content": "質問の中心人物を特定します。"},
                                    {"role": "user", "content": warmup_prompt_character}
                                ],
                                temperature=0,
                                log_label="キャッシュウォームアップ（登場人物）"
                            )

                            logger.info(f"✅ character_summary.txt キャッシュ作成完了（{len(character_summary):,} 文字）")

                    except Exception as e:
                        logger.warning(f"⚠️ 登場人物情報キャッシュ作成失敗（続行します）: {e}")

                    st.session_state.cache_warmed_up = True
                    logger.info("✅ Prompt Cache ウォームアップ完了")

                except Exception as e:
                    logger.warning(f"⚠️ キャッシュウォームアップ失敗（続行します）: {e}")
                    # エラーが発生してもシステムは続行
                    st.session_state.cache_warmed_up = True

    # セッション初回のみウォームアップを実行
    warmup_prompt_cache()

    # =================================================
    # 登場人物あらすじを読み込み（セッションごとに1回のみ）
    # =================================================
    def load_character_summary() -> str:
        """
        character_summary.txtを読み込む
        セッション状態にキャッシュして、複数回の読み込みを防止
        """
        # セッション状態にキャッシュがあればそれを返す
        if "character_summary_cache" in st.session_state:
            return st.session_state.character_summary_cache

        try:
            summary_file = "character_summary_DEMO.txt" if DEMO_MODE else "character_summary.txt"
            summary_path = Path(summary_file)
            if summary_path.exists():
                summary = summary_path.read_text(encoding="utf-8")
                # セッション状態にキャッシュ
                st.session_state.character_summary_cache = summary
                logger.info(f"{summary_file} を読み込みました（{len(summary):,} 文字）")
                return summary
            else:
                logger.warning(f"{summary_file} が見つかりません")
                return ""
        except Exception as e:
            logger.exception(f"{summary_file} 読み込みエラー: {e}")
            return ""

    # =================================================
    # GPT 4o：登場人物質問の判定（本文使用）
    # =================================================
    @log_io()
    def is_character_question(question: str, story_text: str) -> bool:
        """
        質問が登場人物に関するものかを判定

        Args:
            question: ユーザーの質問
            story_text: 物語の本文全体

        Returns:
            bool: 登場人物に関する質問ならTrue
        """
        # Prompt Caching最適化: 本文を先頭に配置
        prompt = f"""
物語の本文:
{story_text}

---

質問: {question}

この質問が「登場人物」に関するものかを判定してください。
判定基準:
- 登場人物の名前、性格、行動、関係性などについて尋ねている → Yes
- ストーリー全体、世界観、テーマなどについて尋ねている → No

回答: Yes / No のみを出力してください。
"""
        try:
            res = openai_chat(
                "gpt-5.1",
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
    def generate_mermaid_file(question: str, story_text: str, q_num: int,
                             user_dir_path: str, user_name: str, user_number: str,
                             graph_type: str = "main_character") -> str | None:
        """
        2段階プロセス：
        1. GPTでざっくりMermaid図を生成
        2. それをCSVに変換して検証
        3. ルールベースで最終的なMermaid図を構築

        Args:
            question: ユーザーの質問
            story_text: 物語本文全体
            q_num: 質問番号
            user_dir_path: ユーザーディレクトリパス
            user_name: ユーザー名
            user_number: ユーザー番号
            graph_type: グラフタイプ ("main_character" or "all_characters")
        """
        # モード5の場合は中心人物を特定せず全体の人物関係図を生成
        if graph_type == "all_characters":
            main_focus = None
            logger.info(f"[Q{q_num}] グラフタイプ: 全体の人物関係図")
        else:
            # ──────────────────────────
            # Step 1: 質問の中心人物を特定（本文使用）
            # Prompt Caching最適化: 本文を先頭に配置
            # ──────────────────────────
            who_prompt = f"""
物語の本文:
{story_text}

---

質問: {question}

この質問の中心となる登場人物の名前を1つだけ答えてください。

要件:
- 本文に登場する正確な人物名で回答
- 人物名のみを1行で出力（説明不要）

回答:
"""

            try:
                res_who = openai_chat(
                    "gpt-5.1",
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
        # Step 2: Structured Outputsで直接構造化データを取得
        # ──────────────────────────
        # Prompt Caching最適化: 本文を先頭に配置
        if graph_type == "all_characters":
            # モード5: 全体の人物関係図
            structured_prompt = f"""
本文:
{story_text}

質問: {question}

タスク: 本文を読み、登場する全ての重要な人物の関係図を構造化データで出力してください。
特定の中心人物を設定せず、物語全体の人物関係を網羅的に表現してください。

【重要な注意事項】
❌ 絶対にやってはいけないこと:
- 「不明」「質問者」「主体」「客体」などの抽象的な人物名は使用禁止
- 実在しない人物を含めない

✅ 正しい例:
- center_person: "ミナ"  （またはnull）
- relationships: [
    {{"source": "ミナ", "target": "アリオス", "relation_type": "bidirectional", "label": "仲間", "group": "勇者パーティー"}},
    {{"source": "ミナ", "target": "レイン", "relation_type": "bidirectional", "label": "元仲間", "group": ""}}
  ]

要件:
1. 実在する登場人物のみ（具体的な人物名）
2. 主要な関係のみ（全体図の場合は10-20人程度、中心人物がある場合は5-10人程度）
3. 関係タイプ:
   - directed: 一方向（上司→部下など）
   - bidirectional: 双方向（友人、仲間など）
   - dotted: 補助的な関係
4. labelは簡潔に（5文字以内推奨）
5. 同じ2人の間の関係は最大2本まで

**絶対に守ること:**
- 「不明」「主体」「客体」などの抽象的な名前は絶対に使用しない
- 必ず実在する登場人物のみを使用する
"""
        else:
            # モード1,3,4: 中心人物を指定した関係図
            structured_prompt = f"""
本文:
{story_text}

質問: {question}
中心人物: {main_focus}

タスク: 本文を読み、{main_focus}を中心とした登場人物の関係図を構造化データで出力してください。

【重要な注意事項】
❌ 絶対にやってはいけないこと:
- 「不明」「質問者」「主体」「客体」などの抽象的な人物名は使用禁止
- 実在しない人物を含めない

✅ 正しい例:
- center_person: "ミナ"
- relationships: [
    {{"source": "ミナ", "target": "アリオス", "relation_type": "bidirectional", "label": "仲間", "group": "勇者パーティー"}},
    {{"source": "ミナ", "target": "レイン", "relation_type": "bidirectional", "label": "元仲間", "group": ""}}
  ]

要件:
1. {main_focus}を必ず含める
2. 実在する登場人物のみ（具体的な人物名）
3. 主要な関係のみ（5-10人程度）
4. 関係タイプ:
   - directed: 一方向（上司→部下など）
   - bidirectional: 双方向（友人、仲間など）
   - dotted: 補助的な関係
5. labelは簡潔に（5文字以内推奨）
6. 同じ2人の間の関係は最大2本まで

**絶対に守ること:**
- 「不明」「主体」「客体」などの抽象的な名前は絶対に使用しない
- 必ず実在する登場人物のみを使用する
- {main_focus}自身を必ず含める
"""

        try:
            # Structured Outputs APIを使用
            response = client.beta.chat.completions.parse(
                model="gpt-5.1",  # GPT-5.1に変更
                messages=[
                    {"role": "system", "content": "登場人物の関係図を構造化データで出力します。"},
                    {"role": "user", "content": structured_prompt}
                ],
                response_format=CharacterGraph,
                temperature=0.3
            )

            graph_data = response.choices[0].message.parsed

            # デバッグ: 生のリレーションシップデータをログ出力
            raw_rels = []
            for i, rel in enumerate(graph_data.relationships):
                raw_rels.append({
                    'index': i,
                    'source': rel.source if rel.source else '[EMPTY]',
                    'target': rel.target if rel.target else '[EMPTY]',
                    'label': rel.label if rel.label else '[EMPTY]',
                    'type': rel.relation_type
                })
            logger.debug(f"[Q{q_num}] Raw relationships from API: {raw_rels}")
            logger.info(f"[Q{q_num}] Structured data: {len(graph_data.relationships)} relationships")

            # Mermaid図を構築
            final_mermaid = build_mermaid_from_structured(graph_data)
            logger.debug(f"[Q{q_num}] Final Mermaid length = {len(final_mermaid)} chars")
            logger.debug(f"[Q{q_num}] Final Mermaid =\n{final_mermaid}")

        except Exception:
            logger.exception("[Mermaid] Structured generation error")
            # フォールバック: 最小限のMermaid図を生成
            final_mermaid = f"graph LR\n    {main_focus}"

        # ──────────────────────────
        # Step 3: Kroki APIでSVG生成（リトライ付き）
        # ──────────────────────────
        mmd_path = Path(user_dir_path) / f"{user_name}_{user_number}_{q_num}.mmd"
        svg_path = mmd_path.with_suffix(".svg")

        # Mermaidファイルを保存
        mmd_path.write_text(final_mermaid, encoding="utf-8")

        import base64
        import zlib
        import requests

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # MermaidコードをKroki形式でエンコード（zlib + base64）
                compressed = zlib.compress(final_mermaid.encode('utf-8'), 6)
                encoded = base64.urlsafe_b64encode(compressed).decode('utf-8')

                # Kroki APIのURL（SVG形式）
                api_url = f"https://kroki.io/mermaid/svg/{encoded}"

                # SVG画像をダウンロード
                response = requests.get(api_url, timeout=30)

                # エラーレスポンスの詳細をログ出力
                if response.status_code != 200:
                    logger.error(f"[Q{q_num}] Kroki API error (attempt {retry_count + 1}/{max_retries}): status={response.status_code}, response={response.text[:500]}")
                    logger.error(f"[Q{q_num}] Sent Mermaid code:\n{final_mermaid}")

                response.raise_for_status()

                # SVGファイルとして保存
                svg_path.write_text(response.text, encoding="utf-8")
                logger.info(f"[Q{q_num}] SVG generated successfully via Kroki API")
                return str(svg_path)

            except Exception as e:
                retry_count += 1
                logger.warning(f"[Q{q_num}] Mermaid SVG generation failed (attempt {retry_count}/{max_retries}): {e}")

                if retry_count < max_retries:
                    # 再生成を試みる
                    logger.info(f"[Q{q_num}] Retrying with new Mermaid generation...")
                    st.info(f"🔄 図の生成に失敗しました。再生成しています... ({retry_count}/{max_retries})")

                    try:
                        # Structured Outputs APIで再度生成
                        response = client.beta.chat.completions.parse(
                            model="gpt-5.1",
                            messages=[
                                {"role": "system", "content": "登場人物の関係図を構造化データで出力します。"},
                                {"role": "user", "content": structured_prompt}
                            ],
                            response_format=CharacterGraph,
                            temperature=0.3
                        )

                        graph_data = response.choices[0].message.parsed
                        logger.info(f"[Q{q_num}] Retry: Structured data: {len(graph_data.relationships)} relationships")

                        # Mermaid図を再構築
                        final_mermaid = build_mermaid_from_structured(graph_data)
                        logger.debug(f"[Q{q_num}] Retry: Final Mermaid length = {len(final_mermaid)} chars")

                        # Mermaidファイルを更新
                        mmd_path.write_text(final_mermaid, encoding="utf-8")

                    except Exception as retry_error:
                        logger.exception(f"[Q{q_num}] Retry generation failed: {retry_error}")
                        # 再生成に失敗した場合は次のループで同じMermaidコードを使う
                        continue
                else:
                    # 最大リトライ回数に達した
                    logger.error(f"[Q{q_num}] Failed Mermaid code after {max_retries} attempts:\n{final_mermaid}")
                    st.warning("⚠️ Mermaid 図生成に失敗しました。生成されたコードを表示します。")
                    st.code(final_mermaid, language="mermaid")
                    st.error(f"エラー詳細: {e}")
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

        st.session_state.page = real_page_index

        # pages_uiは表示用のフォーマット済みテキスト
        current_page_text = pages_ui[st.session_state.ui_page]

        st.markdown(
            f"""
            <div style="
                padding:20px;border-radius:10px;
                background-color:var(--background-color);
                color:var(--text-color);
                border:1px solid var(--secondary-background-color);
                font-size:18px;line-height:1.8;white-space:pre-wrap;
                min-height:500px;max-height:600px;overflow-y:auto;">
            {current_page_text}
            </div>
            """, unsafe_allow_html=True
        )

        # ページナビゲーションを本文の下に配置
        nav1, nav2, nav3 = st.columns([1, 3, 1])
        with nav1:
            if st.button("◀ 前へ", disabled=(st.session_state.ui_page == 0), key="nav_prev"):
                st.session_state.ui_page -= 1
                st.rerun()
        with nav2:
            st.markdown(f"<center>ページ {real_page_index + 1} / {total_pages}</center>",
                        unsafe_allow_html=True)
        with nav3:
            if st.button("次へ ▶",
                         disabled=(st.session_state.ui_page >= total_ui_pages-1), key="nav_next"):
                st.session_state.ui_page += 1
                st.rerun()

        st.markdown("### 💬 質問")
        user_input_text = st.text_area(
            "この小説について質問してください",
            height=100,
            key="question_input",
            placeholder="例: 主人公の名前は何ですか？"
        )

        # モード2の場合は送信ボタンを表示するが、システムは応答しない
        if EXPERIMENT_MODE == 2:
            send_button = st.button("📤 送信（記録のみ）", type="primary", use_container_width=True)
        else:
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
                            f'<div style="background-color:var(--secondary-background-color);'
                            f'color:var(--text-color);padding:10px;border-radius:10px;margin:5px 0;'
                            f'border-left:4px solid #4CAF50;">'
                            f'<b>質問:</b> {item["content"]}</div>',
                            unsafe_allow_html=True)
                    elif item["type"] == "answer":
                        st.markdown(
                            f'<div style="background-color:var(--secondary-background-color);'
                            f'color:var(--text-color);padding:10px;border-radius:10px;margin:5px 0;'
                            f'border-left:4px solid #2196F3;">'
                            f'<b>回答:</b> {item["content"]}</div>',
                            unsafe_allow_html=True)
                    elif item["type"] == "image" and Path(item["path"]).exists():
                        st.image(item["path"], caption=item["caption"],
                                 width="stretch")

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
                width="stretch"
            )
        else:
            st.info("ログファイルがまだ作成されていません")

    # =================================================
    #               ユーザー入力処理
    # =================================================
    if user_input:
        st.session_state.question_number += 1
        q_num = st.session_state.question_number

        # 質問時刻と現在の章番号を取得
        from datetime import datetime
        question_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_chapter = pages_all[real_page_index]["section"] if real_page_index < len(pages_all) else "N/A"
        current_title = pages_all[real_page_index]["title"] if real_page_index < len(pages_all) else "N/A"

        # ログに質問時刻と章番号を記録
        logger.info(f"[Q{q_num}] 時刻: {question_time} | 現在の章: {current_chapter} ({current_title}) | 質問: {user_input}")

        # 質問を履歴に追加
        st.session_state.chat_history.append(
            {"type": "question", "number": q_num, "content": user_input,
             "timestamp": question_time, "chapter": current_chapter, "chapter_title": current_title}
        )

        # 質問をすぐに表示
        st.markdown(
            f'<div style="background-color:var(--secondary-background-color);'
            f'color:var(--text-color);padding:10px;border-radius:10px;margin:5px 0;'
            f'border-left:4px solid #4CAF50;">'
            f'<b>質問:</b> {user_input}</div>',
            unsafe_allow_html=True)

        # モード2の場合は質問を記録するのみで処理を終了
        if EXPERIMENT_MODE == 2:
            st.info("✅ 質問を記録しました（このモードではシステムは応答しません）")
            st.rerun()

        # コンテキスト範囲を決定
        if CURRENT_MODE["context_range"] == "all":
            # デモモードなど、全てのページを使用
            context_end_index = real_page_index + 1
        else:
            # 指定された章数までを使用
            context_end_index = min(CURRENT_MODE["context_range"], len(pages_all))

        # pages_allは辞書形式なので、テキストに変換
        story_text_so_far = "\n\n".join([
            f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
            for sec in pages_all[:context_end_index]
        ])

        # デバッグ：コンテキスト範囲をログに記録
        logger.info(f"[Q{q_num}] コンテキスト範囲: 1~{context_end_index}章 (設定値={CURRENT_MODE['context_range']}, 総章数={len(pages_all)}, 文字数={len(story_text_so_far):,})")

        # 登場人物質問かどうか判定（本文を使用）
        is_char_question = is_character_question(user_input, story_text_so_far)

        # 毎回新しいmessagesを作成（Prompt Caching最適化）
        # キャッシュ可能な本文を先頭に配置
        prompt = f"""以下はユーザーがこれまでに読んだ小説本文です。

----- 本文ここから -----
{story_text_so_far}
----- 本文ここまで -----

# 指示
この本文の内容を根拠にユーザーの質問に日本語で丁寧に答えてください。
**重要: 回答は100文字程度で簡潔にまとめてください。**

質問: {user_input}"""

        # 毎回新しいmessagesを作成（トークン爆発を防ぐ）
        messages = [
            {"role": "system", "content": "あなたは読んでいる小説について質問に答えるアシスタントです。"},
            {"role": "user", "content": prompt}
        ]

        # 並行処理の準備
        svg_file = None
        mermaid_code = None
        reply = None

        try:
            # グラフ生成の有無を判定（モード設定とキャラクター質問の両方を考慮）
            should_generate_graph = CURRENT_MODE["use_graph"] and is_char_question

            if should_generate_graph:
                # 図の生成と回答生成を並行実行
                status_placeholder = st.empty()
                status_placeholder.info("💭 登場人物の関係図と回答を生成中...")

                # スレッドに渡す値を事前に取得（Streamlitコンテキストの外で使用するため）
                user_name = st.session_state.user_name
                user_number = st.session_state.user_number

                with ThreadPoolExecutor(max_workers=2) as executor:
                    # 2つのタスクを並行実行
                    diagram_future = executor.submit(
                        generate_mermaid_file,
                        user_input,
                        story_text_so_far,
                        q_num,
                        str(user_dir),
                        user_name,
                        user_number,
                        CURRENT_MODE["graph_type"]  # モード設定からグラフタイプを取得
                    )
                    answer_future = executor.submit(
                        openai_chat,
                        "gpt-5.1",  # GPT-5.1を使用
                        messages,
                        log_label="質問への回答生成",
                        temperature=0.7
                    )

                    # 両方の結果を取得（並行処理）
                    svg_file = diagram_future.result()
                    resp = answer_future.result()
                    reply = resp.choices[0].message.content.strip()

                status_placeholder.empty()

                # 図の表示
                if svg_file:
                    st.session_state.chat_history.append(
                        {"type": "image",
                         "path": svg_file,
                         "caption": f"登場人物関係図 (質問 #{q_num})"})
                    st.image(svg_file, caption=f"登場人物関係図 (質問 #{q_num})", width="stretch")

                    # Mermaidコードを読み込む
                    mmd_path = Path(svg_file).with_suffix(".mmd")
                    if mmd_path.exists():
                        mermaid_code = mmd_path.read_text(encoding="utf-8")
            else:
                # グラフ生成不要の場合は回答のみ生成
                status_placeholder = st.empty()
                status_placeholder.info("💭 回答を生成中...")

                resp = openai_chat(
                    "gpt-5.1",  # GPT-5.1を使用
                    messages=messages,
                    temperature=0.7,
                    log_label="質問への回答生成"
                )
                reply = resp.choices[0].message.content.strip()
                status_placeholder.empty()

            # 回答を履歴に追加（表示用のみ）
            st.session_state.chat_history.append(
                {"type": "answer", "content": reply}
            )
            logger.info(f"[A{q_num}] 回答生成完了")

            # Google SheetsにQAログを記録
            logger.info(f"[Q{q_num}] log_qa()呼び出し準備: sheets_qa_logger={'あり' if sheets_qa_logger else 'なし'}, svg_file={svg_file}, drive_uploader={'あり' if drive_uploader else 'なし'}")
            if sheets_qa_logger:
                logger.info(f"[Q{q_num}] sheets_qa_logger.log_qa()を呼び出します")
                sheets_qa_logger.log_qa(
                    user_name=st.session_state.user_name,
                    user_number=st.session_state.user_number,
                    q_num=q_num,
                    question=user_input,
                    answer=reply,
                    mermaid_code=mermaid_code,
                    svg_path=svg_file,
                    drive_uploader=drive_uploader,
                    timestamp=question_time,
                    chapter=current_chapter,
                    chapter_title=current_title
                )
                logger.info(f"[Q{q_num}] sheets_qa_logger.log_qa()呼び出し完了")
            else:
                logger.warning(f"[Q{q_num}] sheets_qa_loggerがNoneのため、QAログを記録できません")

        except Exception as e:
            if 'status_placeholder' in locals():
                status_placeholder.empty()
            err = f"エラーが発生しました: {e}"
            st.session_state.chat_history.append(
                {"type": "answer", "content": err}
            )
            st.error(err)
            logger.exception("回答生成失敗")

        st.rerun()
