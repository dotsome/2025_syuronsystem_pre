"""
Mermaid図生成ベンチマーク (30章制限 & バグ修正版)

変更点:
1. load_test_data: 最初の30セクション(章)のみを読み込むように変更
2. run_process_combination: 本文を200文字でカットしていたバグを修正し、全文(30章分)を渡すように変更
"""

import os
import json
import time
import csv
import re
import zlib
import base64
import io
import requests
import xlsxwriter
import logging
from pathlib import Path
from dotenv import load_dotenv
import openai
from tqdm import tqdm

# 環境変数読み込み
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ OPENAI_API_KEY が設定されていません")
    exit(1)

client = openai.OpenAI(api_key=api_key)

FIXED_MODEL = "gpt-4.1"

# ===============================================
#  ロガーの設定
# ===============================================
logger = logging.getLogger("BenchLogger")
logger.handlers.clear()
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("benchmark_debug.log", encoding='utf-8', mode='w')
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(file_handler)

class TqdmLoggingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET): super().__init__(level)
    def emit(self, record):
        try: tqdm.write(self.format(record)); self.flush()
        except Exception: self.handleError(record)

console_handler = TqdmLoggingHandler(level=logging.INFO)
console_handler.setFormatter(logging.Formatter('   %(message)s'))
logger.addHandler(console_handler)

# ===============================================
#  データ読み込み (★ここを修正: 30章制限)
# ===============================================
def load_test_data(filename="beast_text.json"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            story_sections = json.load(f)
        
        # ★ 修正: 最初の30章分だけを取得
        target_sections = story_sections[:30]
        logger.info(f"📖 本文データ: 最初の {len(target_sections)} 章分を読み込みました")

        story_text = "\n\n".join([
            f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
            for sec in target_sections
        ])
        return story_text
    except Exception as e:
        logger.error(f"データ読み込みエラー: {e}")
        return "ダミー本文"

def load_character_summary():
    try:
        if os.path.exists("character_summary.txt"):
            with open("character_summary.txt", "r", encoding="utf-8") as f: return f.read()
    except: pass
    return "ダミーあらすじ"

def build_mermaid_from_csv(csv_text: str, main_focus: str = None) -> str:
    nodes = set(); edges = []; groups = {}; edge_map = {}
    reader = csv.reader(csv_text.splitlines())
    for row in reader:
        if len(row) < 4: continue
        src = row[0].strip(); rel_type = row[1].strip() if len(row)>1 else "directed"
        rel_label = row[2].strip() if len(row)>2 else "関係"; dst = row[3].strip() if len(row)>3 else ""
        group = row[4].strip() if len(row)>4 else ""
        if not src or not dst: continue
        edge_key = (src, dst)
        if edge_key in edge_map: continue
        nodes.add(src); nodes.add(dst)
        if group:
            if group not in groups: groups[group] = set()
            groups[group].add(src); groups[group].add(dst)
        edge_symbol = "-->"
        if rel_type.lower() in ["bidirectional", "双方向"]: edge_symbol = "<-->"
        elif rel_type.lower() in ["dotted", "点線"]: edge_symbol = "-.->"
        edges.append({"src": src, "dst": dst, "symbol": edge_symbol, "label": rel_label[:5]})
        edge_map[edge_key] = True

    lines = ["graph LR"]
    def safe_id(name: str) -> str: return f'id_{abs(hash(name)) % 10000}'
    node_ids = {name: safe_id(name) for name in nodes}
    for name in sorted(nodes): lines.append(f'    {node_ids[name]}["{name}"]')
    if groups:
        for gn, gnodes in groups.items():
            safe_gn = re.sub(r'[^0-9A-Za-z_\u3040-\u30FF\u4E00-\u9FFF\s]', '', gn)
            lines.append(f'\n    subgraph {safe_gn}')
            for n in gnodes: 
                if n in node_ids: lines.append(f'        {node_ids[n]}')
            lines.append('    end')
    lines.append('')
    for e in edges:
        if e["src"] in node_ids and e["dst"] in node_ids:
            sid = node_ids[e["src"]]; did = node_ids[e["dst"]]
            lines.append(f'    {sid} {e["symbol"]}|{e["label"]}| {did}' if e["label"] else f'    {sid} {e["symbol"]} {did}')
    if main_focus and main_focus in node_ids:
        lines.append(f'\n    style {node_ids[main_focus]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
    return '\n'.join(lines)

def get_mermaid_png(code: str) -> bytes:
    if not code: return None
    try:
        compressed = zlib.compress(code.encode('utf-8'), 9)
        encoded = base64.urlsafe_b64encode(compressed).decode('utf-8')
        res = requests.get(f"https://kroki.io/mermaid/png/{encoded}", timeout=10)
        return res.content if res.status_code == 200 else None
    except: return None

# ===============================================
#  LLM呼び出し関数 (Temperature制御)
# ===============================================
def call_llm_safe(model: str, messages: list, temperature: float = 1.0):
    params = {"model": model, "messages": messages}
    # 推論系モデル(gpt-5, o1, o3)はtemperatureを除外
    if not any(x in model for x in ["gpt-5", "o1", "o3"]):
        params["temperature"] = temperature
    return client.chat.completions.create(**params)

# ===============================================
#  メイン処理ロジック (★バグ修正済み)
# ===============================================
def run_process_combination(mermaid_model: str, answer_model: str, question: str, story_text: str, character_summary: str) -> dict:
    result = {
        'mermaid_model': mermaid_model, 'answer_model': answer_model,
        'total_time': 0, 'steps': {}, 'total_tokens': 0,
        'mermaid_code': '', 'error': None, 'question': question, 'answer': ''
    }
    total_tokens = 0
    logger.info(f"▶ 開始: {mermaid_model} / {answer_model} | Q: {question}")

    try:
        # Step 0: Check
        t0 = time.time()
        logger.info(f"  [Step 0] 登場人物判定 ({FIXED_MODEL})...")
        check_msg = [{"role": "user", "content": f"登場人物情報:\n{character_summary}\n\n---\n\n質問: {question}\n\nこの質問が「登場人物」に関するものかを判定してください。\n回答: Yes / No"}]
        res_check = call_llm_safe(FIXED_MODEL, check_msg, temperature=0)
        step0_time = time.time() - t0
        result['steps']['0_check'] = step0_time
        total_tokens += res_check.usage.total_tokens
        logger.info(f"    => 完了 ({step0_time:.2f}s)")

        # Step 1: Focus
        t0 = time.time()
        logger.info(f"  [Step 1] 中心人物特定 ({FIXED_MODEL})...")
        who_msg = [{"role": "user", "content": f"登場人物情報:\n{character_summary}\n\n---\n\n質問: {question}\n\nこの質問の中心となる登場人物の名前を1つだけ答えてください。\n回答:"}]
        res_who = call_llm_safe(FIXED_MODEL, who_msg, temperature=0)
        main_focus = res_who.choices[0].message.content.strip().splitlines()[0]
        step1_time = time.time() - t0
        result['steps']['1_focus'] = step1_time
        total_tokens += res_who.usage.total_tokens
        logger.info(f"    => 特定: {main_focus} ({step1_time:.2f}s)")

        # Step 2: Gen
        t0 = time.time()
        logger.info(f"  [Step 2] ラフ生成 ({mermaid_model})...")
        # ★修正: story_text[:200] を story_text (全文) に変更
        rough_msg = [{"role": "user", "content": f"本文:\n{story_text}\n\n質問: {question}\n要件: graph LRで{main_focus}を中心に関係図を作成..."}]
        res_rough = call_llm_safe(mermaid_model, rough_msg, temperature=0.3)
        rough_mermaid = res_rough.choices[0].message.content.strip().replace('```mermaid', '').replace('```', '').strip()
        step2_time = time.time() - t0
        result['steps']['2_gen'] = step2_time
        total_tokens += res_rough.usage.total_tokens
        logger.info(f"    => 生成完了 ({step2_time:.2f}s)")

        # Step 3: CSV
        t0 = time.time()
        logger.info(f"  [Step 3] CSV変換 ({mermaid_model})...")
        csv_msg = [{"role": "user", "content": f"Mermaid図:\n{rough_mermaid}\n\nこれを主体,関係タイプ,関係詳細,客体,グループのCSVに変換してください..."}]
        res_csv = call_llm_safe(mermaid_model, csv_msg, temperature=0)
        csv_text = res_csv.choices[0].message.content.strip()
        step3_time = time.time() - t0
        result['steps']['3_csv'] = step3_time
        total_tokens += res_csv.usage.total_tokens
        logger.info(f"    => 変換完了 ({step3_time:.2f}s)")

        # Step 4
        final_mermaid = build_mermaid_from_csv(csv_text, main_focus)
        diagram_flow_time = step0_time + step1_time + step2_time + step3_time

        # Step 5: Ans
        t0 = time.time()
        logger.info(f"  [Step 5] 回答生成 ({answer_model})...")
        # ★修正: story_text[:200] を story_text (全文) に変更
        ans_msg = [{"role": "user", "content": f"本文:\n{story_text}\n\n質問: {question}\n\n回答してください。"}]
        res_ans = call_llm_safe(answer_model, ans_msg, temperature=0.7)
        result['answer'] = res_ans.choices[0].message.content.strip()
        step5_time = time.time() - t0
        result['steps']['5_ans'] = step5_time
        total_tokens += res_ans.usage.total_tokens
        logger.info(f"    => 回答完了 ({step5_time:.2f}s)")

        result['total_time'] = max(diagram_flow_time, step5_time)
        result['total_tokens'] = total_tokens
        result['mermaid_code'] = final_mermaid
        logger.info(f"✅ 完了: {result['total_time']:.2f}s")

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"❌ エラー発生: {str(e)}")

    return result

# ===============================================
#  Excel出力
# ===============================================
def save_to_excel(results, output_file="benchmark_30chapters.xlsx"):
    logger.info(f"📊 Excelファイルを生成中: {output_file}...")
    workbook = xlsxwriter.Workbook(output_file)
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1, 'align': 'center'})
    cell_fmt = workbook.add_format({'border': 1, 'text_wrap': True, 'valign': 'top'})
    num_fmt = workbook.add_format({'border': 1, 'num_format': '0.00', 'valign': 'top'})
    code_fmt = workbook.add_format({'border': 1, 'font_name': 'Courier New', 'font_size': 9, 'text_wrap': True, 'valign': 'top'})
    
    ws_sum = workbook.add_worksheet("Summary")
    headers = ["Mermaid Model", "Answer Model", "Runs", "S0 Check", "S1 Focus", "S2 Gen", "S3 CSV", "S5 Ans", "Total"]
    ws_sum.write_row('B2', headers, header_fmt)
    
    grouped = {}
    for r in results:
        key = (r['mermaid_model'], r['answer_model'])
        if key not in grouped: grouped[key] = {'c':0,'s0':[],'s1':[],'s2':[],'s3':[],'s5':[],'t':[]}
        if not r['error']:
            g = grouped[key]; g['c']+=1
            g['s0'].append(r['steps']['0_check']); g['s1'].append(r['steps']['1_focus'])
            g['s2'].append(r['steps']['2_gen']); g['s3'].append(r['steps']['3_csv'])
            g['s5'].append(r['steps']['5_ans']); g['t'].append(r['total_time'])

    row = 2
    for (m_mmd, m_ans), d in grouped.items():
        if d['c']==0: continue
        avgs = [sum(d[k])/d['c'] for k in ['s0','s1','s2','s3','s5','t']]
        ws_sum.write(row, 1, m_mmd, cell_fmt); ws_sum.write(row, 2, m_ans, cell_fmt)
        ws_sum.write(row, 3, d['c'], cell_fmt)
        for i, avg in enumerate(avgs): ws_sum.write(row, 4+i, avg, num_fmt)
        row += 1
    ws_sum.set_column('B:C', 18); ws_sum.set_column('D:J', 12)

    for r in results: 
        safe_m = r['mermaid_model'].replace("gpt-", ""); safe_a = r['answer_model'].replace("gpt-", "")
        sheet_name = f"{safe_m}_{safe_a}_{r.get('q_id','Q')}_{r.get('run','1')}"[:31]
        ws = workbook.add_worksheet(sheet_name)
        ws.set_column('A:A', 25); ws.set_column('B:B', 70)
        data = [("Question", r['question']), ("Mermaid Model", r['mermaid_model']),
                ("Answer Model", r['answer_model']), ("Total Time", f"{r['total_time']:.2f} s"),
                ("Tokens", r['total_tokens'])]
        for i, (l, v) in enumerate(data): ws.write(i+1, 0, l, header_fmt); ws.write(i+1, 1, str(v), cell_fmt)
        curr = len(data) + 2
        if r['error']:
            ws.write(curr, 0, "Error", header_fmt); ws.write(curr, 1, r['error'], cell_fmt)
        else:
            ws.write(curr, 0, "Answer", header_fmt); ws.write(curr, 1, r['answer'], cell_fmt); curr+=1
            ws.write(curr, 0, "Mermaid", header_fmt); ws.write(curr, 1, r['mermaid_code'], code_fmt); curr+=1
            ws.write(curr, 0, "Image", header_fmt)
            png = get_mermaid_png(r['mermaid_code'])
            if png: ws.insert_image(curr, 1, sheet_name, {'image_data': io.BytesIO(png), 'x_scale':0.7, 'y_scale':0.7})
    workbook.close()
    logger.info(f"💾 Excel保存完了: {output_file}")

# ===============================================
#  メイン実行
# ===============================================
def run_benchmark():
    print("🚀 ベンチマーク開始 (30章制限版)...")
    logger.info("=== Benchmark Started ===")
    
    story_text = load_test_data()
    char_summary = load_character_summary()
    
    questions = [
        {"id": "Q1", "text": "ミナって誰だっけ？"},
        {"id": "Q2", "text": "タニアとカナデの関係性について教えて"},
        {"id": "Q3", "text": "レインはアリオスのことがなんで嫌いなの？"},
        {"id": "Q4", "text": "タニアとリーンの関係性について教えて"}
    ]
    
    combinations = [
        ("gpt-4.1", "gpt-4.1"),
        ("gpt-4.1", "gpt-5-mini"),
        ("gpt-4o", "gpt-4o"),
        ("gpt-4o-mini", "gpt-4o-mini"),
        ("gpt-5-mini", "gpt-5-mini"),
        ("gpt-5.1", "gpt-4.1"),
        ("gpt-5.1", "gpt-5-mini"),
    ]
    
    num_runs = 1
    tasks = []
    for (m_mmd, m_ans) in combinations:
        for q in questions:
            for i in range(num_runs):
                tasks.append({'m_mmd': m_mmd, 'm_ans': m_ans, 'q_id': q['id'], 'text': q['text'], 'run': i+1})
    
    with tqdm(total=len(tasks), desc="Total Progress") as pbar:
        results = []
        for task in tasks:
            res = run_process_combination(task['m_mmd'], task['m_ans'], task['text'], story_text, char_summary)
            res['q_id'] = task['q_id']; res['run'] = task['run']
            results.append(res)
            pbar.update(1)

    save_to_excel(results, "benchmark_30chapters.xlsx")
    print(f"詳細ログは 'benchmark_debug.log' を確認してください。")

if __name__ == "__main__":
    run_benchmark()