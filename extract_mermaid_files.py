#!/usr/bin/env python3
"""
モデル比較実験の結果JSONからMermaidファイルを抽出するスクリプト
"""
import json
from pathlib import Path

def extract_mermaid_files(json_file: str, output_dir: str = "mermaid_outputs"):
    """
    JSONファイルからMermaidコードを抽出して個別ファイルとして保存

    Args:
        json_file: 入力JSONファイルパス
        output_dir: 出力ディレクトリ
    """
    # 出力ディレクトリを作成
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # JSONを読み込み
    with open(json_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    print(f"📊 {len(results)}件のテスト結果を処理します")
    print(f"📂 出力先: {output_path.absolute()}\n")

    # 各テスト結果からMermaidコードを抽出
    for i, result in enumerate(results, 1):
        question_id = result['question_id']
        mermaid_model = result['mermaid_model']
        answer_model = result['answer_model']
        mermaid_code = result['outputs'].get('mermaid_code', '')

        if not mermaid_code:
            print(f"⚠️  [{i}] {question_id} - Mermaidコードが空です")
            continue

        # ファイル名を生成: Q1_gpt-5.1_gpt-4.1.mmd
        filename = f"{question_id}_{mermaid_model}_{answer_model}.mmd"
        # ファイル名に使えない文字を置換
        filename = filename.replace('/', '-').replace('\\', '-')

        output_file = output_path / filename

        # Mermaidコードを保存
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)

        print(f"✅ [{i}] {filename} ({len(mermaid_code)} 文字)")

    print(f"\n✨ 完了! {output_path.absolute()} にMermaidファイルを保存しました")

if __name__ == "__main__":
    # 最新の詳細結果ファイルを使用
    json_file = "model_comparison_detailed_20251117_184043.json"

    if not Path(json_file).exists():
        print(f"❌ ファイルが見つかりません: {json_file}")
        exit(1)

    extract_mermaid_files(json_file)
