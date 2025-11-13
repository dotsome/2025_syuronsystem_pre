# ===============================================
#  実験用システム（改良版）
#          ── 2段階Mermaid生成システム ──
# ===============================================
import os, json, subprocess, logging, re, time, csv
from pathlib import Path
from functools import wraps
from logging.handlers import RotatingFileHandler
import streamlit as st
from dotenv import load_dotenv
import openai
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

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
    logger.addHandler(h_file)

    # Console
    h_term = logging.StreamHandler()
    h_term.setFormatter(logging.Formatter(fmt_term))
    h_term.setLevel(logging.INFO)
    h_term.addFilter(ContextFilter())
    logger.addHandler(h_term)

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
# OpenAI 呼び出しラッパ
# -------------------------------------------------
@log_io(300)   # プロンプト冒頭 300 文字だけ記録
def openai_chat(model: str, messages: list[dict], **kw):
    return client.chat.completions.create(
        model=model,
        messages=messages,
        **kw
    )

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
yaml_path = "config.yaml"
with open(yaml_path) as file:
    config = yaml.load(file, Loader=SafeLoader)

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

# =================================================
#          OpenAI クライアント初期化
# =================================================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY が設定されていません。")
    st.stop()

client = openai.OpenAI(api_key=api_key)

st.title(f"📖 実験用システム - "
         f"{st.session_state.user_name} / {st.session_state.user_number}")

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
            temperature=0
        )
        answer = res.choices[0].message.content.strip().lower()
        return "yes" in answer
    except Exception as e:
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
            temperature=0
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
以下の質問と本文を基に、「{main_focus}」を中心とした登場人物の関係を表すMermaid図を生成してください。

質問: {question}

本文:
{story_text}

要件:
- graph LR または graph TD で開始
- {main_focus}を中心に配置し、関連する人物との関係を明確に表現
- 登場人物をノードとして表現
- 関係性を矢印で表現
- 必要に応じてsubgraphでグループ化
- 双方向の関係は <--> で表現
- 一方向の関係は --> で表現
- 点線矢印 -.-> も使用可
- エッジには日本語でラベルを付ける
- {main_focus}に直接または間接的に関わる人物を優先的に含める

出力はMermaidコードのみ（説明不要）
"""
    
    try:
        res_rough = openai_chat(
            "gpt-4.1",  # 高速化のため
            messages=[
                {"role": "system", "content": "Mermaid図を生成する専門家です。"},
                {"role": "user", "content": rough_mermaid_prompt}
            ],
            temperature=0.3
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
特に「{main_focus}」に関連する関係を優先的に抽出してください。

Mermaid図:
{rough_mermaid}

本文（参考）:
{story_text[:2000]}  # 長すぎる場合は冒頭のみ

出力形式:
主体,関係タイプ,関係詳細,客体,グループ

説明:
- 主体: 関係の起点となる人物
- 関係タイプ: directed（一方向）, bidirectional（双方向）, dotted（点線）
- 関係詳細: 関係を表す日本語（10文字以内）
- 客体: 関係の終点となる人物  
- グループ: subgraphに属する場合はグループ名、なければ空欄

注意:
- ヘッダーは不要
- 本文に存在しない人物関係は除外
- {main_focus}に関連する重要度の高い順に並べる
"""

    try:
        res_csv = openai_chat(
            "gpt-4.1",
            messages=[
                {"role": "system", "content": "Mermaid図と本文を照合して正確な関係を抽出します。"},
                {"role": "user", "content": csv_prompt}
            ],
            temperature=0
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
        """
        # ノードとエッジの収集
        nodes = set()
        edges = []
        groups = {}  # グループ名 -> ノードリスト
        
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
                "label": rel_label[:10]  # 10文字制限
            })
        
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
    # Step 6: Mermaid CLIでPNG生成
    # ──────────────────────────
    mmd_path = Path(user_dir) / f"{st.session_state.user_name}_{st.session_state.user_number}_{q_num}.mmd"
    png_path = mmd_path.with_suffix(".png")
    
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
        # Mermaid CLIでPNG生成
        result = subprocess.run(
            ["mmdc", "-i", str(mmd_path), "-o", str(png_path),
             "-t", "default", "-b", "white"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        logger.info(f"[Q{q_num}] PNG generated successfully")
        return str(png_path)
        
    except FileNotFoundError:
        st.error("❌ mmdc が見つかりません。`npm install -g @mermaid-js/mermaid-cli` を実行してください。")
        st.code(final_mermaid, language="mermaid")
        return None
    except subprocess.CalledProcessError as e:
        st.warning("⚠️ Mermaid 図生成に失敗しました。生成されたコードを表示します。")
        st.code(final_mermaid, language="mermaid")
        st.error(f"エラー詳細: {e.stderr}")
        logger.exception(f"Mermaid generation failed: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        st.warning("⚠️ Mermaid 図生成がタイムアウトしました。")
        st.code(final_mermaid, language="mermaid")
        logger.warning("Mermaid generation timeout")
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
    user_input = st.chat_input("この小説について質問できます", key="main_input")

    st.markdown("---")
    info1, info2, info3 = st.columns(3)
    info1.metric("ユーザー",   st.session_state.user_name)
    info2.metric("ナンバー",   st.session_state.user_number)
    info3.metric("質問数",     st.session_state.question_number)

# -------------------------------------------------
# 右：履歴 & 図 & ログ DL
# -------------------------------------------------
with right_col:
    st.markdown("### 📝 質問・回答履歴")
    chat_box = st.container(height=650)

    with chat_box:
        if not st.session_state.chat_history:
            st.info("まだ質問がありません。左側の入力欄から質問してください。")
        else:
            for item in st.session_state.chat_history:
                if item["type"] == "question":
                    st.markdown(
                        f'<div style="background:#DCF8C6;padding:10px;border-radius:10px;margin:5px 0;">'
                        f'<b>Q{item["number"]}:</b> {item["content"]}</div>',
                        unsafe_allow_html=True)
                elif item["type"] == "answer":
                    st.markdown(
                        f'<div style="background:#F1F0F0;padding:10px;border-radius:10px;margin:5px 0;">'
                        f'<b>A:</b> {item["content"]}</div>',
                        unsafe_allow_html=True)
                elif item["type"] == "image" and Path(item["path"]).exists():
                    st.image(item["path"], caption=item["caption"],
                             width='stretch')

    st.markdown("### 📥 ログ")
    with open(log_file, "r", encoding="utf-8") as f:
        st.download_button("ログをダウンロード", f.read(),
                           file_name=log_file.name, mime="text/plain")

# =================================================
#               ユーザー入力処理
# =================================================
if user_input:
    st.session_state.question_number += 1
    q_num = st.session_state.question_number
    logger.info(f"[Q{q_num}] {user_input}")

    st.session_state.chat_history.append(
        {"type": "question", "number": q_num, "content": user_input}
    )

    thinking_msg = f"『{user_input}』について思考中です…"
    idx_thinking = len(st.session_state.chat_history)
    st.session_state.chat_history.append(
        {"type": "answer", "content": thinking_msg, "tmp": True}
    )

    story_text_so_far = "\n\n".join(pages_all[:real_page_index + 1])

    png_file = None
    if is_character_question(user_input):
        with st.spinner("登場人物の関係図を生成中..."):
            png_file = generate_mermaid_file(user_input, story_text_so_far, q_num)
            if png_file:
                st.session_state.chat_history.append(
                    {"type": "image",
                     "path": png_file,
                     "caption": f"登場人物関係図 (質問 #{q_num})"})

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
        with st.spinner("回答を生成中..."):
            resp  = openai_chat(
                        "gpt-4.1",
                        messages=st.session_state.messages,
                        temperature=0.7
                    )
            reply = resp.choices[0].message.content.strip()

        st.session_state.chat_history[idx_thinking] = {
            "type": "answer", "content": reply
        }
        st.session_state.messages.append(
            {"role": "assistant", "content": reply})
        logger.info(f"[A{q_num}] 回答生成完了")

    except Exception as e:
        err = f"エラーが発生しました: {e}"
        st.session_state.chat_history[idx_thinking] = {
            "type": "answer", "content": err
        }
        st.error(err)
        logger.exception("回答生成失敗")

    st.rerun()
