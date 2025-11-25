#!/usr/bin/env python3
"""
全てのMermaidファイルのハイライト状態を確認
"""
from pathlib import Path
import json

def check_all_highlighting():
    """全ての.mmdファイルのハイライト状態をチェック"""
    mermaid_dir = Path("mermaid_outputs")

    # JSONファイルから中心人物情報を取得
    json_file = Path("model_comparison_detailed_20251125_043721.json")
    with open(json_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    # 中心人物のマップを作成
    center_person_map = {}
    for result in results:
        q_id = result['question_id']
        mermaid_model = result['mermaid_model']
        answer_model = result['answer_model']
        center_person = result['outputs']['center_person']
        base_filename = f"{q_id}_{mermaid_model}_{answer_model}"
        center_person_map[base_filename] = center_person

    print("=" * 80)
    print("Mermaidファイルのハイライト状態チェック")
    print("=" * 80)
    print()

    highlighted = []
    not_highlighted = []

    # 最終出力のみをチェック（_roughファイルは除外）
    for mmd_file in sorted(mermaid_dir.glob("Q*_gpt-*.mmd")):
        # _roughファイルをスキップ
        if "_rough" in mmd_file.stem:
            continue

        base_filename = mmd_file.stem
        center_person = center_person_map.get(base_filename, "不明")

        with open(mmd_file, 'r', encoding='utf-8') as f:
            content = f.read()

        has_highlight = 'style' in content and 'fill:#FFD700' in content
        file_size = len(content)

        if has_highlight:
            highlighted.append((base_filename, center_person, file_size))
            print(f"✅ {base_filename}")
            print(f"   中心人物: {center_person} | サイズ: {file_size}文字")
        else:
            not_highlighted.append((base_filename, center_person, file_size))
            print(f"❌ {base_filename}")
            print(f"   中心人物: {center_person} | サイズ: {file_size}文字")

    print()
    print("=" * 80)
    print(f"✅ ハイライトあり: {len(highlighted)}/{len(highlighted) + len(not_highlighted)}")
    print(f"❌ ハイライトなし: {len(not_highlighted)}/{len(highlighted) + len(not_highlighted)}")
    print(f"成功率: {len(highlighted) / (len(highlighted) + len(not_highlighted)) * 100:.1f}%")
    print("=" * 80)

    if not_highlighted:
        print()
        print("【ハイライトなしのファイル詳細】")
        for filename, center, size in not_highlighted:
            print(f"  - {filename}")
            print(f"    中心人物: {center}")
            print(f"    ファイルサイズ: {size}文字")

            # 内容を確認
            mmd_file = mermaid_dir / f"{filename}.mmd"
            with open(mmd_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if size < 20:
                print(f"    ⚠️  空グラフ（期待通り）")
            else:
                print(f"    ⚠️  調査が必要")
                # 中心人物がノードとして存在するか確認
                if center in content:
                    print(f"    📝 '{center}' はグラフ内に存在")
                else:
                    print(f"    ⚠️  '{center}' がグラフ内に見つからない")

if __name__ == "__main__":
    check_all_highlighting()
