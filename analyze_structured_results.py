#!/usr/bin/env python3
"""
Structured Outputs版ベンチマーク結果の分析
"""
import json
from pathlib import Path
from collections import defaultdict

# 結果読み込み
with open('model_comparison_structured_20251125_135628.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

print("=" * 80)
print("Structured Outputs版ベンチマーク結果分析")
print("=" * 80)
print()

# 基本統計
total_tests = len(results)
print(f"総テスト数: {total_tests}")
print()

# モデル別統計
model_stats = defaultdict(lambda: {
    'count': 0,
    'total_time': 0,
    'mermaid_time': 0,
    'answer_time': 0,
    'total_tokens': 0,
    'cached_tokens': 0
})

for result in results:
    key = (result['mermaid_model'], result['answer_model'])
    model_stats[key]['count'] += 1
    model_stats[key]['total_time'] += result['total_time']

    # プロセス別時間
    model_stats[key]['mermaid_time'] += result['processes']['mermaid_generation']['time']
    model_stats[key]['answer_time'] += result['processes']['answer_generation']['time']

    # トークン統計
    for process in result['processes'].values():
        model_stats[key]['total_tokens'] += process['tokens']['prompt'] + process['tokens']['completion']
        model_stats[key]['cached_tokens'] += process['tokens']['cached']

print("モデル組み合わせ別統計:")
print("-" * 80)
print(f"{'Mermaidモデル':<15} {'回答モデル':<15} {'平均時間(秒)':<15} {'Mermaid(秒)':<15} {'回答(秒)':<15} {'キャッシュ率'}")
print("-" * 80)

for (mermaid_model, answer_model), stats in sorted(model_stats.items()):
    count = stats['count']
    avg_time = stats['total_time'] / count
    avg_mermaid = stats['mermaid_time'] / count
    avg_answer = stats['answer_time'] / count
    cache_rate = (stats['cached_tokens'] / stats['total_tokens'] * 100) if stats['total_tokens'] > 0 else 0

    print(f"{mermaid_model:<15} {answer_model:<15} {avg_time:<15.2f} {avg_mermaid:<15.2f} {avg_answer:<15.2f} {cache_rate:.1f}%")

print()

# メタノードチェック
INVALID_NODES = {'不明', '主体', '客体', 'グループ', '関係タイプ', '関係詳細', '?', '？'}

meta_node_count = 0
highlight_count = 0

for result in results:
    mermaid_code = result['outputs']['mermaid_code']

    # メタノードチェック
    has_meta = any(node in mermaid_code for node in INVALID_NODES)
    if has_meta:
        meta_node_count += 1

    # ハイライトチェック
    if 'style' in mermaid_code and 'fill:#FFD700' in mermaid_code:
        highlight_count += 1

print("品質指標:")
print("-" * 80)
print(f"メタノード率: {meta_node_count}/{total_tests} ({meta_node_count/total_tests*100:.1f}%)")
print(f"ハイライト率: {highlight_count}/{total_tests} ({highlight_count/total_tests*100:.1f}%)")
print()

# 関係数の統計
relationship_counts = [r['outputs']['relationships_count'] for r in results]
avg_relationships = sum(relationship_counts) / len(relationship_counts)
min_relationships = min(relationship_counts)
max_relationships = max(relationship_counts)

print("関係数統計:")
print("-" * 80)
print(f"平均関係数: {avg_relationships:.1f}")
print(f"最小関係数: {min_relationships}")
print(f"最大関係数: {max_relationships}")
print()

# 処理時間の詳細
all_times = [r['total_time'] for r in results]
all_mermaid_times = [r['processes']['mermaid_generation']['time'] for r in results]
all_answer_times = [r['processes']['answer_generation']['time'] for r in results]

print("処理時間統計:")
print("-" * 80)
print(f"平均合計時間: {sum(all_times)/len(all_times):.2f}秒")
print(f"最小合計時間: {min(all_times):.2f}秒")
print(f"最大合計時間: {max(all_times):.2f}秒")
print()
print(f"平均Mermaid生成: {sum(all_mermaid_times)/len(all_mermaid_times):.2f}秒")
print(f"平均回答生成: {sum(all_answer_times)/len(all_answer_times):.2f}秒")
print()

# トークン統計
total_prompt_tokens = sum(
    sum(p['tokens']['prompt'] for p in r['processes'].values())
    for r in results
)
total_completion_tokens = sum(
    sum(p['tokens']['completion'] for p in r['processes'].values())
    for r in results
)
total_cached_tokens = sum(
    sum(p['tokens']['cached'] for p in r['processes'].values())
    for r in results
)

print("トークン使用量:")
print("-" * 80)
print(f"総Promptトークン: {total_prompt_tokens:,}")
print(f"総Completionトークン: {total_completion_tokens:,}")
print(f"総Cachedトークン: {total_cached_tokens:,}")
print(f"キャッシュ率: {total_cached_tokens/total_prompt_tokens*100:.1f}%")
print()

print("=" * 80)
print("✨ 分析完了")
print("=" * 80)
