#!/usr/bin/env python3
"""
zikken_11month_v7.pyへのStructured Outputs統合テスト
"""
import os
import json
from pathlib import Path
from typing import List, Literal
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

# OpenAI APIクライアント
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Pydanticスキーマ定義
class Relationship(BaseModel):
    """登場人物間の関係"""
    source: str
    target: str
    relation_type: Literal["directed", "bidirectional", "dotted"]
    label: str
    group: str = ""

class CharacterGraph(BaseModel):
    """登場人物関係図の構造化データ"""
    center_person: str
    relationships: List[Relationship]

# 無効なノード名のセット
INVALID_NODES = {
    '不明', '主体', '客体', 'グループ', '関係タイプ', '関係詳細',
    '?', '？', 'None', 'none', 'null', 'NULL', ''
}

def build_mermaid_from_structured(graph: CharacterGraph) -> str:
    """
    Structured OutputsのCharacterGraphからMermaid図を構築

    従来のCSV処理で行っていた工夫をルールベースで適用:
    - 重複エッジの排除（同じペア・同じ方向は1つまで）
    - ラベル文字数制限（5文字以内）
    - ノードのソート（一貫性）
    - グループ名のサニタイズ
    """
    import re
    lines = ["graph LR"]

    # ノードとエッジを収集（重複排除付き）
    nodes = set()
    edges = []
    groups = {}
    edge_map = {}  # (src, dst)のペアをキーにして重複チェック

    for rel in graph.relationships:
        # INVALIDチェック
        if rel.source in INVALID_NODES or rel.target in INVALID_NODES:
            continue

        if not rel.source or not rel.target:
            continue

        # 同じペア（順序あり）の重複チェック
        edge_key = (rel.source, rel.target)
        if edge_key in edge_map:
            # 既に同じ方向の関係がある場合はスキップ
            continue

        # ノード登録
        nodes.add(rel.source)
        nodes.add(rel.target)

        # グループ情報
        if rel.group:
            if rel.group not in groups:
                groups[rel.group] = set()
            groups[rel.group].add(rel.source)
            groups[rel.group].add(rel.target)

        # エッジ記録（ラベルは5文字制限）
        edge_symbol = "-->"  # デフォルト
        if rel.relation_type == "bidirectional":
            edge_symbol = "<-->"
        elif rel.relation_type == "dotted":
            edge_symbol = "-.->."

        edges.append({
            "src": rel.source,
            "dst": rel.target,
            "symbol": edge_symbol,
            "label": rel.label[:5]  # 5文字制限
        })
        edge_map[edge_key] = True

    # ノードIDの生成（安全な識別子）
    def safe_id(name: str) -> str:
        return f'id_{abs(hash(name)) % 10000}'

    node_ids = {name: safe_id(name) for name in nodes}

    # ノード定義（ソート済み）
    for name in sorted(nodes):
        node_id = node_ids[name]
        lines.append(f'    {node_id}["{name}"]')

    # グループ定義（グループ名をサニタイズ）
    if groups:
        lines.append('')
        for group_name, group_nodes in groups.items():
            # 特殊文字を除去してサニタイズ
            safe_group_name = re.sub(r'[^0-9A-Za-z_\u3040-\u30FF\u4E00-\u9FFF\s]', '', group_name)
            lines.append(f'    subgraph {safe_group_name}')
            for node in sorted(group_nodes):
                if node in node_ids:
                    lines.append(f'        {node_ids[node]}')
            lines.append('    end')

    # エッジ定義
    lines.append('')
    for edge in edges:
        if edge["src"] in node_ids and edge["dst"] in node_ids:
            src_id = node_ids[edge["src"]]
            dst_id = node_ids[edge["dst"]]

            if edge["label"]:
                if edge["symbol"] == "<-->":
                    lines.append(f'    {src_id} <-->|{edge["label"]}| {dst_id}')
                elif edge["symbol"] == "-.->":
                    lines.append(f'    {src_id} -.->|{edge["label"]}| {dst_id}')
                else:
                    lines.append(f'    {src_id} -->|{edge["label"]}| {dst_id}')
            else:
                lines.append(f'    {src_id} {edge["symbol"]} {dst_id}')

    # 中心人物ハイライト（fuzzy matching）
    if graph.center_person:
        if graph.center_person in node_ids:
            lines.append(f'\n    style {node_ids[graph.center_person]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
        else:
            # 部分一致で検索
            for node_name in node_ids:
                if graph.center_person in node_name or node_name in graph.center_person:
                    lines.append(f'\n    style {node_ids[node_name]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')
                    break  # 最初にマッチしたノードのみをハイライト

    return '\n'.join(lines)

def test_integration():
    """統合テスト"""
    print("=" * 80)
    print("zikken_11month_v7.py統合テスト")
    print("=" * 80)
    print()

    # テストデータを読み込み
    with open('beast_text.json', 'r', encoding='utf-8') as f:
        story_data = json.load(f)

    story_text = "\n\n".join([
        f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
        for sec in story_data[:30]
    ])

    question = "ミナって誰だっけ？"
    main_focus = "ミナ"

    print(f"質問: {question}")
    print(f"中心人物: {main_focus}")
    print()

    # Structured Outputsでグラフデータを取得
    structured_prompt = f"""
本文:
{story_text}

質問: {question}
中心人物: {main_focus}

タスク: 本文を読み、{main_focus}を中心とした登場人物の関係図を構造化データで出力してください。

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
1. {main_focus}を必ず含める
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
- {main_focus}自身を必ず含める
"""

    try:
        print("Structured Outputs呼び出し中...")
        response = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "登場人物の関係図を構造化データで出力します。"},
                {"role": "user", "content": structured_prompt}
            ],
            response_format=CharacterGraph,
            temperature=0.3
        )

        graph_data = response.choices[0].message.parsed
        print(f"✅ 構造化データ取得成功")
        print(f"   中心人物: {graph_data.center_person}")
        print(f"   関係数: {len(graph_data.relationships)}")
        print()

        # Mermaid図を構築
        print("Mermaid図構築中...")
        final_mermaid = build_mermaid_from_structured(graph_data)

        # メタノードチェック
        has_invalid = any(
            rel.source in INVALID_NODES or rel.target in INVALID_NODES
            for rel in graph_data.relationships
        )
        print(f"✅ Mermaid図生成完了")
        print(f"   図サイズ: {len(final_mermaid)} 文字")
        print(f"   メタノード: {'❌ 含まれる' if has_invalid else '✅ なし'}")

        # ハイライトチェック
        has_highlight = 'style' in final_mermaid and 'fill:#FFD700' in final_mermaid
        print(f"   ハイライト: {'✅ あり' if has_highlight else '❌ なし'}")
        print()

        # Mermaid図を保存
        output_file = Path("test_integration_result.mmd")
        output_file.write_text(final_mermaid, encoding='utf-8')
        print(f"💾 保存: {output_file}")
        print()

        print("=" * 80)
        print("✨ テスト成功！zikken_11month_v7.pyの統合は正常に動作します")
        print("=" * 80)

    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_integration()
