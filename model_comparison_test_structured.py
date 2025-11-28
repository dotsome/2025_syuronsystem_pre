#!/usr/bin/env python3
# ===============================================
#  モデル比較実験スクリプト (Structured Outputs版)
# ===============================================
import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Literal
from dotenv import load_dotenv
import openai
from pydantic import BaseModel

# 環境変数読み込み
load_dotenv()
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'model_comparison_structured_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =================================================
#           Pydanticスキーマ定義
# =================================================

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

# =================================================
#           テスト設定
# =================================================

# 固定モデル（必ずGPT-5.1を使用）
FIXED_MODELS = {
    "character_judgment": "gpt-5.1",
    "center_person": "gpt-5.1"
}

# テスト対象モデル（Structured Outputs対応モデルのみ）
TEST_MODELS = {
    "structured_mermaid": [
        "gpt-4o",
        "gpt-4o-mini"
    ],
    "answer_generation": [
        "gpt-4o",
        "gpt-4o-mini"
    ]
}

# テスト用の質問
TEST_QUESTIONS = [
    {
        "id": "Q1",
        "question": "ミナって誰だっけ？",
        "type": "character_identification"
    },
    {
        "id": "Q2",
        "question": "タニアとカナデの関係性について教えて",
        "type": "relationship"
    },
    {
        "id": "Q3",
        "question": "レインはアリオスのことがなんで嫌いなの？",
        "type": "character_motivation"
    },
    {
        "id": "Q4",
        "question": "タニアとリーンの関係性について教えて",
        "type": "relationship"
    }
]

# =================================================
#           ヘルパー関数
# =================================================

def openai_chat_timed(model: str, messages: List[Dict], log_label: str = None, **kwargs) -> Dict[str, Any]:
    """OpenAI APIを呼び出し、時間とトークン数を計測"""
    start_time = time.time()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        elapsed = time.time() - start_time

        usage = response.usage
        tokens = {
            "prompt": usage.prompt_tokens if usage else 0,
            "completion": usage.completion_tokens if usage else 0,
            "total": usage.total_tokens if usage else 0,
            "cached": 0
        }

        if hasattr(usage, 'prompt_tokens_details') and hasattr(usage.prompt_tokens_details, 'cached_tokens'):
            tokens['cached'] = usage.prompt_tokens_details.cached_tokens

        content = response.choices[0].message.content if response.choices else ""

        log_msg = f"✓ {log_label or 'API呼び出し'}: model={model}, time={elapsed:.2f}s, tokens={tokens['prompt']}→{tokens['completion']}"
        if tokens['cached'] > 0:
            log_msg += f" (cached: {tokens['cached']})"
        logger.info(log_msg)

        return {
            "response": response,
            "time": elapsed,
            "tokens": tokens,
            "content": content
        }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ API呼び出し失敗: {e}")
        raise

# =================================================
#           Structured Outputs関数
# =================================================

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

def process_structured_mermaid(model: str, story_text: str, question: str,
                               center_person: str) -> Dict[str, Any]:
    """
    Structured Outputsでグラフ生成（1ステップ）
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

    try:
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

        usage = response.usage
        tokens = {
            "prompt": usage.prompt_tokens if usage else 0,
            "completion": usage.completion_tokens if usage else 0,
            "total": usage.total_tokens if usage else 0,
            "cached": 0
        }

        if hasattr(usage, 'prompt_tokens_details') and hasattr(usage.prompt_tokens_details, 'cached_tokens'):
            tokens['cached'] = usage.prompt_tokens_details.cached_tokens

        graph_data = response.choices[0].message.parsed
        mermaid_code = build_mermaid_from_structured(graph_data)

        logger.info(f"✓ Structured Mermaid生成({model}): time={elapsed:.2f}s, tokens={tokens['prompt']}→{tokens['completion']}, cached={tokens['cached']}, relationships={len(graph_data.relationships)}")

        return {
            "response": response,
            "time": elapsed,
            "tokens": tokens,
            "content": mermaid_code,
            "graph_data": graph_data
        }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ Structured Mermaid生成失敗: {e}")
        raise

def process_center_person(story_text: str, question: str, character_summary: str) -> Dict[str, Any]:
    """中心人物特定プロセス（固定: GPT-5.1）"""
    prompt = f"""登場人物情報:
{character_summary}

---

質問: {question}

この質問の中心となる登場人物の名前を1つだけ答えてください。

要件:
- 登場人物情報に記載されている正確な人物名で回答
- 人物名のみを1行で出力（説明不要）

回答:"""

    messages = [
        {"role": "system", "content": "質問の中心人物を特定します。"},
        {"role": "user", "content": prompt}
    ]

    return openai_chat_timed(
        model=FIXED_MODELS["center_person"],
        messages=messages,
        log_label="中心人物特定",
        temperature=0.0
    )

def process_answer_generation(model: str, story_text: str, question: str,
                              mermaid_code: str) -> Dict[str, Any]:
    """回答生成プロセス"""
    prompt = f"""以下の本文と登場人物関係図を参考に、質問に回答してください。

本文:
{story_text}

登場人物関係図:
{mermaid_code}

質問: {question}

回答:"""

    messages = [
        {"role": "system", "content": "質問に回答するアシスタントです。"},
        {"role": "user", "content": prompt}
    ]

    kwargs = {"log_label": f"回答生成({model})", "temperature": 0.7}

    return openai_chat_timed(
        model=model,
        messages=messages,
        **kwargs
    )

# =================================================
#           ベンチマーク実行
# =================================================

def run_benchmark():
    """Structured Outputs版ベンチマーク"""
    logger.info("=" * 80)
    logger.info("モデル比較実験 (Structured Outputs版)")
    logger.info("=" * 80)

    # データ読み込み
    with open('beast_text.json', 'r', encoding='utf-8') as f:
        story_data = json.load(f)

    with open('character_summary.txt', 'r', encoding='utf-8') as f:
        character_summary = f.read()

    story_text = "\n\n".join([
        f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
        for sec in story_data[:30]
    ])

    results = []
    output_dir = Path("mermaid_outputs_structured")
    output_dir.mkdir(exist_ok=True)

    # =================================================
    # Prompt Cacheウォームアップ（初回高速化）
    # =================================================
    logger.info("🔥 Prompt Cacheウォームアップ中...")
    try:
        # ダミー質問でキャッシュ作成（各モデルごと）
        warmup_question = "主人公について教えてください"

        # 中心人物特定のウォームアップ
        _ = process_center_person(story_text, warmup_question, character_summary)

        # Structured Mermaid生成のウォームアップ（各モデル）
        for mermaid_model in TEST_MODELS["structured_mermaid"]:
            _ = process_structured_mermaid(
                mermaid_model,
                story_text,
                warmup_question,
                "主人公"
            )

        # 回答生成のウォームアップ（各モデル）
        dummy_mermaid = "graph LR\n    A[主人公]"
        for answer_model in TEST_MODELS["answer_generation"]:
            _ = process_answer_generation(
                answer_model,
                story_text,
                warmup_question,
                dummy_mermaid
            )

        logger.info("✅ Prompt Cacheウォームアップ完了")
        logger.info("")
    except Exception as e:
        logger.warning(f"⚠️ ウォームアップ失敗（続行します）: {e}")
        logger.info("")

    # テスト組み合わせ
    total_tests = len(TEST_QUESTIONS) * len(TEST_MODELS["structured_mermaid"]) * len(TEST_MODELS["answer_generation"])
    logger.info(f"総テスト数: {total_tests}")
    logger.info("")

    test_count = 0

    for q_info in TEST_QUESTIONS:
        for mermaid_model in TEST_MODELS["structured_mermaid"]:
            for answer_model in TEST_MODELS["answer_generation"]:
                test_count += 1
                logger.info(f"[{test_count}/{total_tests}] {q_info['id']}: {q_info['question']}")
                logger.info(f"  Mermaidモデル: {mermaid_model}, 回答モデル: {answer_model}")

                try:
                    # Step 1: 中心人物特定
                    center_result = process_center_person(story_text, q_info['question'], character_summary)
                    center_person = center_result['content'].strip()

                    # Step 2: Structured Outputsで関係図生成
                    mermaid_result = process_structured_mermaid(
                        mermaid_model,
                        story_text,
                        q_info['question'],
                        center_person
                    )

                    # Step 3: 回答生成
                    answer_result = process_answer_generation(
                        answer_model,
                        story_text,
                        q_info['question'],
                        mermaid_result['content']
                    )

                    # Mermaidファイル保存
                    mmd_file = output_dir / f"{q_info['id']}_{mermaid_model}_{answer_model}.mmd"
                    mmd_file.write_text(mermaid_result['content'], encoding='utf-8')

                    # 結果記録
                    result = {
                        "question_id": q_info['id'],
                        "question": q_info['question'],
                        "question_type": q_info['type'],
                        "mermaid_model": mermaid_model,
                        "answer_model": answer_model,
                        "outputs": {
                            "center_person": center_person,
                            "mermaid_code": mermaid_result['content'],
                            "answer": answer_result['content'],
                            "relationships_count": len(mermaid_result['graph_data'].relationships)
                        },
                        "processes": {
                            "center_person": {
                                "time": center_result['time'],
                                "tokens": center_result['tokens']
                            },
                            "mermaid_generation": {
                                "time": mermaid_result['time'],
                                "tokens": mermaid_result['tokens']
                            },
                            "answer_generation": {
                                "time": answer_result['time'],
                                "tokens": answer_result['tokens']
                            }
                        },
                        "total_time": center_result['time'] + mermaid_result['time'] + answer_result['time']
                    }

                    results.append(result)
                    logger.info(f"  ✅ 完了: {result['total_time']:.2f}秒")

                except Exception as e:
                    logger.error(f"  ❌ エラー: {e}")
                    import traceback
                    traceback.print_exc()

                logger.info("")

    # 結果保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_json = f"model_comparison_structured_{timestamp}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("=" * 80)
    logger.info(f"✨ ベンチマーク完了！ 結果: {output_json}")
    logger.info(f"   総テスト数: {len(results)}/{total_tests}")
    logger.info("=" * 80)

if __name__ == "__main__":
    run_benchmark()
