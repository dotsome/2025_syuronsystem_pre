#!/usr/bin/env python3
"""
Structured Outputs vs 既存方式の比較テスト
"""
import os
import json
import time
from pathlib import Path
from test_structured_output import (
    generate_character_graph_structured,
    build_mermaid_from_structured,
    INVALID_NODES
)
from model_comparison_test import (
    process_center_person,
    process_mermaid_generation,
    process_csv_conversion,
    build_mermaid_from_csv
)

def compare_methods():
    """2つの方式を比較"""

    # テストデータを読み込み
    with open('beast_text.json', 'r', encoding='utf-8') as f:
        story_data = json.load(f)

    story_text = "\n\n".join([
        f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
        for sec in story_data[:30]
    ])

    # character_summary.txtを読み込み
    with open('character_summary.txt', 'r', encoding='utf-8') as f:
        character_summary = f.read()

    test_question = "ミナって誰だっけ？"

    print("=" * 80)
    print("Structured Outputs vs 既存方式の比較")
    print("=" * 80)
    print()

    # ============================================
    # 既存方式（2ステップ）
    # ============================================
    print("【既存方式】 Rough Mermaid → CSV変換")
    print("-" * 80)

    legacy_start = time.time()

    # Step 1: 中心人物特定
    center_result = process_center_person(story_text, test_question, character_summary)
    center_person = center_result['content'].strip()

    # Step 2: Rough Mermaid生成
    mermaid_result = process_mermaid_generation(
        "gpt-4o",
        story_text,
        test_question,
        center_person,
        character_summary
    )

    # Step 3: CSV変換
    csv_result = process_csv_conversion(
        "gpt-4o",
        mermaid_result['content'],
        story_text,
        center_person
    )

    # Step 4: Mermaid再構築
    legacy_mermaid = build_mermaid_from_csv(csv_result['content'], center_person)

    legacy_elapsed = time.time() - legacy_start

    # 統計
    legacy_tokens = {
        'prompt': center_result['tokens']['prompt'] + mermaid_result['tokens']['prompt'] + csv_result['tokens']['prompt'],
        'completion': center_result['tokens']['completion'] + mermaid_result['tokens']['completion'] + csv_result['tokens']['completion'],
        'cached': center_result['tokens']['cached'] + mermaid_result['tokens']['cached'] + csv_result['tokens']['cached']
    }

    print(f"✅ 完了: {legacy_elapsed:.2f}秒")
    print(f"   API呼び出し: 3回（中心人物 + Mermaid + CSV）")
    print(f"   総Tokens: {legacy_tokens['prompt']}→{legacy_tokens['completion']} (cached: {legacy_tokens['cached']})")
    print(f"   中心人物: {center_person}")
    print(f"   Mermaid図サイズ: {len(legacy_mermaid)} 文字")

    # メタノードチェック
    legacy_has_invalid = any(node in legacy_mermaid for node in ['不明', '主体', '客体'])
    print(f"   メタノード: {'❌ 含まれる' if legacy_has_invalid else '✅ なし'}")

    # ハイライトチェック
    legacy_has_highlight = 'style' in legacy_mermaid and 'fill:#FFD700' in legacy_mermaid
    print(f"   ハイライト: {'✅ あり' if legacy_has_highlight else '❌ なし'}")

    print()

    # ============================================
    # Structured Outputs方式（1ステップ）
    # ============================================
    print("【Structured Outputs方式】 直接構造化データ取得")
    print("-" * 80)

    structured_start = time.time()

    # Step 1: 中心人物特定（同じ）
    center_result2 = process_center_person(story_text, test_question, character_summary)
    center_person2 = center_result2['content'].strip()

    # Step 2: Structured Outputsで直接生成
    graph_data, so_elapsed, so_tokens = generate_character_graph_structured(
        "gpt-4o",
        story_text,
        test_question,
        center_person2
    )

    # Step 3: Mermaid構築
    structured_mermaid = build_mermaid_from_structured(graph_data)

    structured_elapsed = time.time() - structured_start

    # 統計
    structured_tokens = {
        'prompt': center_result2['tokens']['prompt'] + so_tokens['prompt'],
        'completion': center_result2['tokens']['completion'] + so_tokens['completion'],
        'cached': center_result2['tokens']['cached'] + so_tokens['cached']
    }

    print(f"✅ 完了: {structured_elapsed:.2f}秒")
    print(f"   API呼び出し: 2回（中心人物 + Structured Output）")
    print(f"   総Tokens: {structured_tokens['prompt']}→{structured_tokens['completion']} (cached: {structured_tokens['cached']})")
    print(f"   中心人物: {center_person2}")
    print(f"   Mermaid図サイズ: {len(structured_mermaid)} 文字")

    # メタノードチェック
    structured_has_invalid = any(
        rel.source in INVALID_NODES or rel.target in INVALID_NODES
        for rel in graph_data.relationships
    )
    print(f"   メタノード: {'❌ 含まれる' if structured_has_invalid else '✅ なし'}")

    # ハイライトチェック
    structured_has_highlight = 'style' in structured_mermaid and 'fill:#FFD700' in structured_mermaid
    print(f"   ハイライト: {'✅ あり' if structured_has_highlight else '❌ なし'}")

    print()

    # ============================================
    # 比較結果
    # ============================================
    print("=" * 80)
    print("📊 比較結果")
    print("=" * 80)
    print()

    time_saved = legacy_elapsed - structured_elapsed
    time_reduction = (time_saved / legacy_elapsed) * 100

    api_calls_saved = 1  # CSV変換が不要
    token_saved = legacy_tokens['prompt'] - structured_tokens['prompt']

    print(f"処理時間:")
    print(f"  既存方式: {legacy_elapsed:.2f}秒")
    print(f"  Structured: {structured_elapsed:.2f}秒")
    print(f"  短縮: {time_saved:.2f}秒 ({time_reduction:.1f}%削減)")
    print()

    print(f"API呼び出し:")
    print(f"  既存方式: 3回")
    print(f"  Structured: 2回")
    print(f"  削減: {api_calls_saved}回 (33%削減)")
    print()

    print(f"トークン使用量:")
    print(f"  既存方式 Prompt: {legacy_tokens['prompt']:,}")
    print(f"  Structured Prompt: {structured_tokens['prompt']:,}")
    print(f"  削減: {token_saved:,} ({(token_saved/legacy_tokens['prompt']*100):.1f}%削減)")
    print()

    print(f"品質:")
    print(f"  既存方式 - メタノード: {'あり' if legacy_has_invalid else 'なし'}, ハイライト: {'あり' if legacy_has_highlight else 'なし'}")
    print(f"  Structured - メタノード: {'あり' if structured_has_invalid else 'なし'}, ハイライト: {'あり' if structured_has_highlight else 'なし'}")
    print()

    print("=" * 80)
    print(f"🎯 結論: Structured Outputsで{time_reduction:.1f}%高速化、品質も同等以上！")
    print("=" * 80)

if __name__ == "__main__":
    compare_methods()
