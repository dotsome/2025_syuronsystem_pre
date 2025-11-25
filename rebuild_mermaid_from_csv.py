#!/usr/bin/env python3
"""
既存のCSVファイルからMermaid図を再生成
- CSVヘッダー行を除去
- 中心人物のハイライトを適用
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from model_comparison_test import build_mermaid_from_csv

def rebuild_all_mermaid():
    """全てのCSVファイルからMermaid図を再生成"""
    print("=" * 80)
    print("既存のCSVファイルからMermaid図を再生成します")
    print("=" * 80)
    print()

    # JSONファイルから中心人物情報を取得
    json_file = Path("model_comparison_detailed_20251125_043721.json")
    with open(json_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    mermaid_dir = Path("mermaid_outputs")
    success_count = 0
    error_count = 0

    for result in results:
        q_id = result['question_id']
        mermaid_model = result['mermaid_model']
        answer_model = result['answer_model']
        center_person = result['outputs']['center_person']

        # ファイル名生成
        base_filename = f"{q_id}_{mermaid_model}_{answer_model}"
        csv_file = mermaid_dir / f"{base_filename}.csv"
        mmd_file = mermaid_dir / f"{base_filename}.mmd"

        # CSVファイルが存在するか確認
        if not csv_file.exists():
            print(f"⏭️  {base_filename}: CSVファイルが見つかりません")
            error_count += 1
            continue

        try:
            # CSVを読み込み
            with open(csv_file, 'r', encoding='utf-8') as f:
                csv_text = f.read()

            # Mermaid図を再生成（ハイライト付き）
            rebuilt_mermaid = build_mermaid_from_csv(csv_text, center_person)

            # ファイルに保存
            with open(mmd_file, 'w', encoding='utf-8') as f:
                f.write(rebuilt_mermaid)

            # ハイライト確認
            has_highlight = 'style' in rebuilt_mermaid and 'fill:#FFD700' in rebuilt_mermaid
            highlight_str = "✨" if has_highlight else "  "

            print(f"{highlight_str} {base_filename}: 再生成完了 ({len(rebuilt_mermaid)}文字)")
            success_count += 1

        except Exception as e:
            print(f"❌ {base_filename}: エラー - {str(e)}")
            error_count += 1

    print()
    print("=" * 80)
    print(f"✅ 完了: {success_count}件成功, {error_count}件エラー")
    print("=" * 80)

if __name__ == "__main__":
    rebuild_all_mermaid()
