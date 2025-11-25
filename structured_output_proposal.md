# Structured Outputsを使ったMermaid図生成の改善提案

## 現在の問題点

### 現在の2ステッププロセス
1. **Step 1**: Rough Mermaid生成（テキスト形式）
2. **Step 2**: CSV変換（GPTで再度パース）

### 問題
- 2回のAPI呼び出しが必要（時間とコスト）
- テキストパース時のエラー（"不明"ノード、フォーマット崩れ）
- CSV形式の検証が不完全

## 提案: Structured Outputs使用

### 新しい1ステッププロセス
**Step 1**: Structured Outputsで直接構造化データ取得

```python
from pydantic import BaseModel
from typing import List, Literal

class Relationship(BaseModel):
    """登場人物間の関係"""
    source: str  # 関係の起点となる人物
    target: str  # 関係の終点となる人物
    relation_type: Literal["directed", "bidirectional", "dotted"]
    label: str  # 関係の詳細（5文字以内推奨）
    group: str = ""  # subgraphグループ名

class CharacterGraph(BaseModel):
    """登場人物関係図の構造化データ"""
    center_person: str  # 中心人物
    relationships: List[Relationship]

# OpenAI API呼び出し
response = client.beta.chat.completions.parse(
    model="gpt-4o",  # Structured Outputsはgpt-4o以降で利用可能
    messages=[
        {"role": "system", "content": "登場人物の関係図を構造化データで出力します。"},
        {"role": "user", "content": prompt}
    ],
    response_format=CharacterGraph
)

# 構造化データを取得
graph_data = response.choices[0].message.parsed
```

## メリット

### 1. API呼び出しの削減
- **Before**: 2回（Rough生成 + CSV変換）
- **After**: 1回（Structured Output）
- **効果**: 約50%の時間短縮、コスト削減

### 2. データ品質の向上
- ✅ スキーマ検証が自動的に行われる
- ✅ "不明"などの無効な値を型レベルで排除可能
- ✅ relation_typeが`Literal`で厳密に制限される
- ✅ パースエラーが発生しない

### 3. コードの簡素化
- CSV変換ステップが不要
- 正規表現によるパース処理が不要
- エラーハンドリングが簡単

### 4. メンテナンス性向上
- Pydanticスキーマで仕様が明確
- 型ヒント付きで開発しやすい
- バリデーションルールを追加しやすい

## 実装例

```python
def generate_character_graph_structured(
    model: str,
    story_text: str,
    question: str,
    center_person: str
) -> CharacterGraph:
    """
    Structured Outputsで登場人物関係図を生成
    """
    prompt = f"""
本文:
{story_text}

質問: {question}
中心人物: {center_person}

タスク: 本文を読み、{center_person}を中心とした登場人物の関係図を構造化データで出力してください。

要件:
- {center_person}を必ず含める
- 実在する登場人物のみ（「不明」「主体」などの抽象ノードは禁止）
- 主要な関係のみ（5-10人程度）
- 関係タイプ:
  * directed: 一方向（上司→部下など）
  * bidirectional: 双方向（友人、仲間など）
  * dotted: 補助的な関係
"""

    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "登場人物の関係図を構造化データで出力します。"},
            {"role": "user", "content": prompt}
        ],
        response_format=CharacterGraph,
        temperature=0.3
    )

    return response.choices[0].message.parsed


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
                node_id = f"id_{hash(person) % 10000}"
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
    for group_name, members in groups.items():
        lines.append(f'\n    subgraph {group_name}')
        for member in set(members):
            if member in nodes:
                lines.append(f'        {nodes[member]}')
        lines.append('    end')

    # 関係定義
    for rel in graph.relationships:
        if rel.source in INVALID_NODES or rel.target in INVALID_NODES:
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

    # 中心人物ハイライト
    if graph.center_person in nodes:
        lines.append(f'\n    style {nodes[graph.center_person]} fill:#FFD700,stroke:#FF8C00,stroke-width:4px')

    return '\n'.join(lines)
```

## 移行計画

### Phase 1: プロトタイプ実装
1. Pydanticスキーマ定義
2. Structured Outputs呼び出し実装
3. 既存システムと並行テスト

### Phase 2: 検証
1. 品質比較（既存 vs Structured Outputs）
2. 速度・コスト比較
3. エラー率の測定

### Phase 3: 本番投入
1. 既存コードの置き換え
2. 旧ステップの削除
3. ドキュメント更新

## 期待される効果

| 指標 | Before | After | 改善 |
|------|--------|-------|------|
| API呼び出し | 2回 | 1回 | -50% |
| 処理時間 | ~10秒 | ~5秒 | -50% |
| メタノード率 | 7.1% | ~0% | -100% |
| パースエラー | 時々発生 | なし | -100% |

## 注意点

1. **モデル制限**: Structured OutputsはGPT-4o以降のみ対応
2. **スキーマサイズ**: あまり複雑なスキーマは避ける
3. **互換性**: 既存のMermaidファイルとの互換性を保つ

## 結論

Structured Outputsの導入により、より高速で正確なMermaid図生成が可能になります。
特に「不明」ノード問題の完全解決と、処理速度の大幅向上が期待できます。
