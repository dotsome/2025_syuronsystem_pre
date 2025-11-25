#!/usr/bin/env python3
"""
Structured Outputsを使ったMermaid図生成のテスト
"""
import os
import json
import time
from pathlib import Path
from typing import List, Literal
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

# OpenAI APIクライアント
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================
# Pydanticスキーマ定義
# ============================================

class Relationship(BaseModel):
    """登場人物間の関係"""
    source: str  # 関係の起点となる人物
    target: str  # 関係の終点となる人物
    relation_type: Literal["directed", "bidirectional", "dotted"]  # 関係のタイプ
    label: str  # 関係の詳細（5文字以内推奨）
    group: str = ""  # subgraphグループ名（オプション）

class CharacterGraph(BaseModel):
    """登場人物関係図の構造化データ"""
    center_person: str  # 中心人物
    relationships: List[Relationship]  # 関係のリスト

# ============================================
# Structured Outputsでグラフ生成
# ============================================

def generate_character_graph_structured(
    model: str,
    story_text: str,
    question: str,
    center_person: str
) -> tuple[CharacterGraph, float, dict]:
    """
    Structured Outputsで登場人物関係図を生成

    Returns:
        (CharacterGraph, elapsed_time, token_info)
    """
    prompt = f"""
本文:
{story_text}

質問: {question}
中心人物: {center_person}

タスク: 本文を読み、{center_person}を中心とした登場人物の関係図を構造化データで出力してください。

【重要な注意事項】
❌ 絶対にやってはいけないこと:
- 「不明」「質問者」「主体」「客体」などの抽象的な人物名は使用禁止
- 実在しない人物を含めない

✅ 正しい例:
- center_person: "ミナ"
- relationships: [
    {{"source": "ミナ", "target": "アリオス", "relation_type": "bidirectional", "label": "仲間", "group": "勇者パーティー"}},
    {{"source": "ミナ", "target": "レイン", "relation_type": "bidirectional", "label": "元仲間", "group": ""}}
  ]

要件:
1. {center_person}を必ず含める
2. 実在する登場人物のみ（具体的な人物名）
3. 主要な関係のみ（5-10人程度）
4. 関係タイプ:
   - directed: 一方向（上司→部下など）
   - bidirectional: 双方向（友人、仲間など）
   - dotted: 補助的な関係
5. labelは簡潔に（5文字以内推奨）
6. 同じ2人の間の関係は最大2本まで

**絶対に守ること:**
- 「不明」「主体」「客体」などの抽象的な名前は絶対に使用しない
- 必ず実在する登場人物のみを使用する
- {center_person}自身を必ず含める
"""

    start_time = time.time()

    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "登場人物の関係図を構造化データで出力します。"},
            {"role": "user", "content": prompt}
        ],
        response_format=CharacterGraph,
        temperature=0.3
    )

    elapsed = time.time() - start_time

    # トークン情報を取得
    usage = response.usage
    token_info = {
        "prompt": usage.prompt_tokens if usage else 0,
        "completion": usage.completion_tokens if usage else 0,
        "total": usage.total_tokens if usage else 0,
        "cached": 0
    }

    # Prompt Caching情報を取得
    if hasattr(usage, 'prompt_tokens_details') and hasattr(usage.prompt_tokens_details, 'cached_tokens'):
        token_info['cached'] = usage.prompt_tokens_details.cached_tokens

    graph_data = response.choices[0].message.parsed

    return graph_data, elapsed, token_info

# ============================================
# Mermaid図構築
# ============================================

INVALID_NODES = {
    '不明', '主体', '客体', 'グループ', '関係タイプ', '関係詳細',
    '?', '？', 'None', 'none', 'null', 'NULL', ''
}

def build_mermaid_from_structured(graph: CharacterGraph) -> str:
    """
    構造化データからMermaid図を構築
    """
    lines = ["graph LR"]

    # ノードを収集
    nodes = {}
    groups = {}

    for rel in graph.relationships:
        # INVALIDチェック
        if rel.source in INVALID_NODES or rel.target in INVALID_NODES:
            continue

        # ノード登録
        for person in [rel.source, rel.target]:
            if person not in nodes:
                node_id = f"id_{abs(hash(person)) % 10000}"
                nodes[person] = node_id

        # グループ情報
        if rel.group:
            if rel.group not in groups:
                groups[rel.group] = []
            groups[rel.group].append(rel.source)
            groups[rel.group].append(rel.target)

    # ノード定義
    for person, node_id in nodes.items():
        lines.append(f'    {node_id}["{person}"]')

    # グループ定義
    if groups:
        lines.append('')
        for group_name, members in groups.items():
            lines.append(f'    subgraph {group_name}')
            for member in set(members):
                if member in nodes:
                    lines.append(f'        {nodes[member]}')
            lines.append('    end')

    # 関係定義
    lines.append('')
    for rel in graph.relationships:
        if rel.source in INVALID_NODES or rel.target in INVALID_NODES:
            continue

        if rel.source not in nodes or rel.target not in nodes:
            continue

        src_id = nodes[rel.source]
        tgt_id = nodes[rel.target]

        if rel.relation_type == "bidirectional":
            arrow = "<-->"
        elif rel.relation_type == "dotted":
            arrow = "-.->."
        else:
            arrow = "-->"

        lines.append(f'    {src_id} {arrow}|{rel.label}| {tgt_id}')

    # 中心人物ハイライト（fuzzy matching）
    if graph.center_person:
        if graph.center_person in nodes:
            lines.append(f'\n    style {nodes[graph.center_person]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
        else:
            # 部分一致で検索
            for node_name in nodes:
                if graph.center_person in node_name or node_name in graph.center_person:
                    lines.append(f'\n    style {nodes[node_name]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
                    break

    return '\n'.join(lines)

# ============================================
# テスト実行
# ============================================

def test_structured_output():
    """Structured Outputsのテスト"""

    # テストデータを読み込み
    with open('beast_text.json', 'r', encoding='utf-8') as f:
        story_data = json.load(f)

    # 最初の30章を使用（各章はdictなので整形）
    story_text = "\n\n".join([
        f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
        for sec in story_data[:30]
    ])

    # テストケース
    test_cases = [
        {"question": "ミナって誰だっけ？", "center": "ミナ", "model": "gpt-4o"},
        {"question": "タニアとカナデの関係性について教えて", "center": "タニア", "model": "gpt-4o"},
    ]

    print("=" * 80)
    print("Structured Outputs テスト")
    print("=" * 80)
    print()

    for i, test in enumerate(test_cases, 1):
        print(f"テスト{i}: {test['question']}")
        print(f"モデル: {test['model']}, 中心人物: {test['center']}")
        print("-" * 80)

        try:
            # Structured Outputsで生成
            graph_data, elapsed, tokens = generate_character_graph_structured(
                model=test['model'],
                story_text=story_text,
                question=test['question'],
                center_person=test['center']
            )

            print(f"✅ 生成成功: {elapsed:.2f}秒")
            print(f"   Tokens: {tokens['prompt']}→{tokens['completion']} (cached: {tokens['cached']})")
            print(f"   中心人物: {graph_data.center_person}")
            print(f"   関係数: {len(graph_data.relationships)}")

            # 関係の詳細を表示
            print(f"\n   関係一覧:")
            for rel in graph_data.relationships[:5]:  # 最初の5件
                print(f"     {rel.source} {rel.relation_type} {rel.target} ({rel.label})")

            if len(graph_data.relationships) > 5:
                print(f"     ... 他 {len(graph_data.relationships) - 5} 件")

            # Mermaid図を構築
            mermaid_code = build_mermaid_from_structured(graph_data)
            print(f"\n   Mermaid図サイズ: {len(mermaid_code)} 文字")

            # メタノードチェック
            has_invalid = any(
                rel.source in INVALID_NODES or rel.target in INVALID_NODES
                for rel in graph_data.relationships
            )
            print(f"   メタノード: {'❌ 含まれる' if has_invalid else '✅ なし'}")

            # ハイライトチェック
            has_highlight = 'style' in mermaid_code and 'fill:#FFD700' in mermaid_code
            print(f"   ハイライト: {'✅ あり' if has_highlight else '❌ なし'}")

            # Mermaid図を保存
            output_file = Path(f"test_structured_Q{i}_{test['model']}.mmd")
            output_file.write_text(mermaid_code, encoding='utf-8')
            print(f"   保存: {output_file}")

        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()

        print()

    print("=" * 80)
    print("テスト完了")
    print("=" * 80)

if __name__ == "__main__":
    test_structured_output()
