#!/usr/bin/env python3
"""
モデル比較実験の結果JSONとMermaidファイルを統合するスクリプト
"""
import json
from pathlib import Path
from datetime import datetime

def merge_results_with_mermaid(json_file: str, mermaid_dir: str = "mermaid_outputs"):
    """
    JSONファイルとMermaidファイルを統合

    Args:
        json_file: 入力JSONファイルパス
        mermaid_dir: Mermaidファイルのディレクトリ
    """
    # JSONを読み込み
    with open(json_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    mermaid_path = Path(mermaid_dir)

    print(f"📊 {len(results)}件のテスト結果を処理します")
    print(f"📂 Mermaidディレクトリ: {mermaid_path.absolute()}\n")

    # 各テスト結果にMermaidファイルパスを追加
    updated_results = []
    for i, result in enumerate(results, 1):
        question_id = result['question_id']
        mermaid_model = result['mermaid_model']
        answer_model = result['answer_model']

        # ファイル名を生成
        filename = f"{question_id}_{mermaid_model}_{answer_model}.mmd"
        filename = filename.replace('/', '-').replace('\\', '-')

        mermaid_file = mermaid_path / filename

        # 結果をコピー
        updated_result = result.copy()

        # Mermaidファイル情報を追加
        updated_result['mermaid_file'] = {
            'path': str(mermaid_file),
            'relative_path': str(Path(mermaid_dir) / filename),
            'exists': mermaid_file.exists(),
            'size_bytes': mermaid_file.stat().st_size if mermaid_file.exists() else 0
        }

        updated_results.append(updated_result)

        status = "✅" if mermaid_file.exists() else "❌"
        print(f"{status} [{i}] {question_id} - {filename}")

    # 新しいファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"model_comparison_with_mermaid_{timestamp}.json"

    # 統合結果を保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(updated_results, f, ensure_ascii=False, indent=2)

    print(f"\n✨ 完了! 統合結果を保存しました: {output_file}")
    print(f"   ファイルサイズ: {Path(output_file).stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    # 最新の詳細結果ファイルを使用
    json_file = "model_comparison_detailed_20251117_184043.json"

    if not Path(json_file).exists():
        print(f"❌ ファイルが見つかりません: {json_file}")
        exit(1)

    merge_results_with_mermaid(json_file)
