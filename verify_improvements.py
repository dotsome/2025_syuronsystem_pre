#!/usr/bin/env python3
"""
修正効果を検証するスクリプト
- CSVファイルに「不明」「主体」「客体」などのメタノードが含まれるかチェック
- Mermaid図で中心人物のハイライトが適用されているかチェック
"""
import json
from pathlib import Path
import csv

def check_meta_nodes_in_csv(csv_text: str) -> list:
    """CSVにメタノードが含まれるかチェック"""
    INVALID_NODES = {
        '不明', '主体', '客体', 'グループ', '関係タイプ', '関係詳細',
        '?', '？', 'None', 'none', 'null', 'NULL'
    }

    found_issues = []
    reader = csv.reader(csv_text.splitlines())
    for i, row in enumerate(reader, 1):
        if len(row) >= 2:
            src = row[0].strip()
            dst = row[3].strip() if len(row) >= 4 else row[1].strip()

            if src in INVALID_NODES:
                found_issues.append(f"行{i}: 主体='{src}'")
            if dst in INVALID_NODES:
                found_issues.append(f"行{i}: 客体='{dst}'")

    return found_issues

def check_highlight_in_mermaid(mermaid_text: str) -> bool:
    """Mermaidにハイライト(style)が含まれるかチェック"""
    return 'style' in mermaid_text and 'fill:#FFD700' in mermaid_text

def verify_results():
    """全テスト結果を検証"""
    # 最新のJSONファイルを取得
    json_files = sorted(Path('.').glob('model_comparison_detailed_*.json'))
    if not json_files:
        print("❌ JSONファイルが見つかりません")
        return

    latest_json = json_files[-1]
    print(f"📄 検証対象: {latest_json.name}\n")

    with open(latest_json, 'r', encoding='utf-8') as f:
        results = json.load(f)

    print(f"📊 全テスト数: {len(results)}\n")
    print("=" * 80)

    # 統計
    meta_node_count = 0
    no_highlight_count = 0
    empty_graph_count = 0

    # 詳細結果
    meta_node_cases = []
    no_highlight_cases = []
    empty_graph_cases = []

    for i, result in enumerate(results, 1):
        q_id = result['question_id']
        mermaid_model = result['mermaid_model']
        answer_model = result['answer_model']

        # CSVチェック
        csv_text = result['outputs'].get('csv', '')
        meta_issues = check_meta_nodes_in_csv(csv_text)

        # Mermaidハイライトチェック
        mermaid_text = result['outputs'].get('mermaid', '')
        has_highlight = check_highlight_in_mermaid(mermaid_text)

        # 空グラフチェック
        is_empty = not csv_text or len(csv_text.strip()) < 10

        # 問題を記録
        if meta_issues:
            meta_node_count += 1
            meta_node_cases.append({
                'test': f"{q_id} ({mermaid_model}/{answer_model})",
                'issues': meta_issues
            })

        if not has_highlight:
            no_highlight_count += 1
            no_highlight_cases.append(f"{q_id} ({mermaid_model}/{answer_model})")

        if is_empty:
            empty_graph_count += 1
            empty_graph_cases.append(f"{q_id} ({mermaid_model}/{answer_model})")

    # サマリー表示
    print(f"🔍 検証結果サマリー:")
    print(f"  ✅ ハイライト適用: {len(results) - no_highlight_count}/{len(results)} ({100*(len(results)-no_highlight_count)/len(results):.1f}%)")
    print(f"  ❌ ハイライト未適用: {no_highlight_count}/{len(results)} ({100*no_highlight_count/len(results):.1f}%)")
    print(f"  ⚠️  メタノード含む: {meta_node_count}/{len(results)} ({100*meta_node_count/len(results):.1f}%)")
    print(f"  🚫 空グラフ: {empty_graph_count}/{len(results)} ({100*empty_graph_count/len(results):.1f}%)")
    print("=" * 80)
    print()

    # 詳細表示
    if meta_node_cases:
        print(f"⚠️  メタノードを含むテスト ({meta_node_count}件):")
        for case in meta_node_cases[:10]:  # 最初の10件のみ表示
            print(f"\n  {case['test']}:")
            for issue in case['issues'][:5]:  # 各ケース最大5件
                print(f"    - {issue}")
        if len(meta_node_cases) > 10:
            print(f"\n  ... 他 {len(meta_node_cases) - 10}件")
        print()

    if no_highlight_cases:
        print(f"❌ ハイライト未適用のテスト ({no_highlight_count}件):")
        for case in no_highlight_cases[:10]:
            print(f"  - {case}")
        if len(no_highlight_cases) > 10:
            print(f"  ... 他 {len(no_highlight_cases) - 10}件")
        print()

    if empty_graph_cases:
        print(f"🚫 空グラフのテスト ({empty_graph_count}件):")
        for case in empty_graph_cases[:10]:
            print(f"  - {case}")
        if len(empty_graph_cases) > 10:
            print(f"  ... 他 {len(empty_graph_cases) - 10}件")
        print()

    # 改善度判定
    print("=" * 80)
    if meta_node_count == 0 and no_highlight_count == 0 and empty_graph_count == 0:
        print("🎉 完璧! すべてのテストが期待通りの結果です!")
    elif meta_node_count < len(results) * 0.3:
        print("✅ 改善されました! メタノードの問題が大幅に減少しています")
    else:
        print("❌ 改善が不十分です。プロンプトの強化が必要です")

if __name__ == "__main__":
    verify_results()
