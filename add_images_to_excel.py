import pandas as pd
import subprocess
import io
import os
import xlsxwriter
from tqdm import tqdm
import time

# ==========================================
# 設定
# ==========================================
INPUT_FILE = "benchmark_30chapters.xlsx"
OUTPUT_FILE = "benchmark_30chapters_local_images.xlsx"

# 一時ファイル名
TEMP_MMD = "temp_chart.mmd"
TEMP_PNG = "temp_chart.png"

# ==========================================
# ローカル変換関数 (mermaid-cli使用)
# ==========================================
def render_mermaid_local(code):
    if not code or not isinstance(code, str) or len(code) < 10:
        return None, "コードが空または短すぎます"

    # 1. Mermaidコードを一時ファイルに保存
    try:
        with open(TEMP_MMD, "w", encoding="utf-8") as f:
            f.write(code)
    except Exception as e:
        return None, f"ファイル書き込みエラー: {e}"

    # 2. mmdcコマンドを実行 (Node.jsツール)
    # -i: 入力, -o: 出力, -b: 背景透過, -s: スケール(高画質化)
    cmd = f'mmdc -i "{TEMP_MMD}" -o "{TEMP_PNG}" -b transparent -s 2'
    
    try:
        # タイムアウトを120秒に設定 (巨大な図対策)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            # エラー時は標準エラー出力を返す
            return None, f"Render Error: {result.stderr[:200]}..."
            
        # 3. 生成された画像を読み込む
        if os.path.exists(TEMP_PNG):
            with open(TEMP_PNG, "rb") as f:
                img_data = f.read()
            return img_data, "Success"
        else:
            return None, "出力ファイルが見つかりません"

    except subprocess.TimeoutExpired:
        return None, "Timeout: 処理が重すぎます (120秒超過)"
    except Exception as e:
        return None, f"Execution Error: {e}"
    finally:
        # お掃除
        if os.path.exists(TEMP_MMD): os.remove(TEMP_MMD)
        if os.path.exists(TEMP_PNG): os.remove(TEMP_PNG)
        # Puppeteerの一時ファイルなどが残る場合があるため

# ==========================================
# メイン処理
# ==========================================
def process_excel_images(input_path, output_path):
    print(f"📖 読み込み中: {input_path}")
    
    try:
        all_sheets = pd.read_excel(input_path, sheet_name=None, header=None)
    except FileNotFoundError:
        print(f"❌ ファイルが見つかりません: {input_path}")
        return

    workbook = xlsxwriter.Workbook(output_path)
    
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
    fmt_cell = workbook.add_format({'border': 1, 'text_wrap': True, 'valign': 'top'})
    fmt_code = workbook.add_format({'border': 1, 'font_name': 'Courier New', 'font_size': 9, 'text_wrap': True, 'valign': 'top'})
    fmt_warning = workbook.add_format({'border': 1, 'font_color': 'red', 'valign': 'top'})

    # 進捗バーの設定
    for sheet_name, df in tqdm(all_sheets.items(), desc="ローカルレンダリング中"):
        ws = workbook.add_worksheet(sheet_name[:31])
        ws.set_column('A:A', 25)
        ws.set_column('B:B', 70)

        mermaid_code_found = None
        last_row_index = 0

        # データの転記
        for r_idx, row in df.iterrows():
            last_row_index = r_idx
            vals = [row[i] if pd.notna(row[i]) else "" for i in range(len(row))]
            col0 = str(vals[0])
            
            for c_idx, val in enumerate(vals):
                current_fmt = fmt_cell
                if r_idx == 0 and sheet_name == "Summary": current_fmt = fmt_header
                elif sheet_name != "Summary" and c_idx == 0: current_fmt = fmt_header
                elif "Mermaid Code" in col0 and c_idx == 1: current_fmt = fmt_code
                
                ws.write(r_idx, c_idx, val, current_fmt)

            if sheet_name != "Summary" and ("Mermaid" in col0) and len(vals) > 1:
                code = str(vals[1])
                if "graph" in code or "subgraph" in code:
                    mermaid_code_found = code

        # 画像生成と挿入
        if mermaid_code_found:
            img_row = last_row_index + 1
            ws.write(img_row, 0, "Diagram (Local Render)", fmt_header)
            
            # ★ローカル変換関数を呼び出し
            png_data, status_msg = render_mermaid_local(mermaid_code_found)
            
            if png_data:
                image_stream = io.BytesIO(png_data)
                ws.insert_image(img_row, 1, sheet_name, {
                    'image_data': image_stream,
                    'x_scale': 0.5, 
                    'y_scale': 0.5,
                    'object_position': 1
                })
            else:
                ws.write(img_row, 1, f"画像生成失敗: {status_msg}", fmt_warning)

    workbook.close()
    print(f"\n✅ 完了しました: {output_path}")

if __name__ == "__main__":
    # 念のためコマンド確認
    try:
        subprocess.run("mmdc --version", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        process_excel_images(INPUT_FILE, OUTPUT_FILE)
    except subprocess.CalledProcessError:
        print("❌ エラー: 'mmdc' コマンドが見つかりません。")
        print("以下のコマンドでインストールしてください:")
        print("npm install -g @mermaid-js/mermaid-cli")