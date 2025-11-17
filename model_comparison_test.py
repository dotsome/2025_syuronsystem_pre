#!/usr/bin/env python3
# ===============================================
#  モデル比較実験スクリプト
# ===============================================
import os
import json
import time
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv
import openai

# 環境変数読み込み
load_dotenv()
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'model_comparison_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =================================================
#           テスト設定
# =================================================

# 固定モデル（必ずGPT-5.1を使用）
FIXED_MODELS = {
    "character_judgment": "gpt-5.1",  # 登場人物判定
    "center_person": "gpt-5.1"         # 中心人物特定
}

# テスト対象モデル
TEST_MODELS = {
    "mermaid_csv": [
        "gpt-5.1",
        "gpt-5-mini",
        "gpt-4-2025-08-07",
        "gpt-4.1",
        "gpt-4o",
        "gpt-4o-mini"
    ],
    "answer_generation": [
        "gpt-5-mini",
        "gpt-4-2025-08-07",
        "gpt-4.1",
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
    """
    OpenAI APIを呼び出し、時間とトークン数を計測

    Returns:
        dict: {
            "response": ChatCompletion,
            "time": float,
            "tokens": {"prompt": int, "completion": int, "total": int},
            "content": str
        }
    """
    start_time = time.time()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        elapsed = time.time() - start_time

        # トークン使用量
        usage = response.usage
        tokens = {
            "prompt": usage.prompt_tokens if usage else 0,
            "completion": usage.completion_tokens if usage else 0,
            "total": usage.total_tokens if usage else 0
        }

        content = response.choices[0].message.content if response.choices else ""

        log_msg = f"✓ {log_label or 'API呼び出し'}: model={model}, time={elapsed:.2f}s, tokens={tokens['prompt']}→{tokens['completion']}"
        logger.info(log_msg)

        return {
            "response": response,
            "time": elapsed,
            "tokens": tokens,
            "content": content
        }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"✗ {log_label or 'API呼び出し'}失敗: model={model}, time={elapsed:.2f}s, error={str(e)}")
        return {
            "response": None,
            "time": elapsed,
            "tokens": {"prompt": 0, "completion": 0, "total": 0},
            "content": f"ERROR: {str(e)}",
            "error": str(e)
        }


def load_story_text() -> str:
    """
    小説本文を読み込み（31ページまで）

    zikken_11month_v7.pyと同じ形式で、31ページ目（START_PAGE=30, 実際のページindex=30）まで読み込む
    """
    START_PAGE = 30  # zikken_11month_v7.pyと同じ設定
    story_file = Path(__file__).parent / "beast_text.json"

    if story_file.exists():
        with open(story_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # zikken_11month_v7.pyと同じ形式でページを作成
        pages_all = [f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
                     for sec in data]

        # 31ページ目まで（index 0-30 = 31ページ）
        story_text = "\n\n".join(pages_all[:START_PAGE + 1])

        logger.info(f"小説本文を読み込みました: {START_PAGE + 1}ページ, {len(story_text)}文字")
        return story_text
    else:
        logger.warning(f"小説ファイルが見つかりません: {story_file}")
        return "（サンプルテキスト）これは小説の本文です。"


def load_character_summary() -> str:
    """登場人物要約を読み込み"""
    summary_file = Path(__file__).parent / "character_summary.txt"
    if summary_file.exists():
        with open(summary_file, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        logger.warning(f"登場人物要約ファイルが見つかりません: {summary_file}")
        return ""


# =================================================
#           各プロセスの実行関数
# =================================================

def process_character_judgment(story_text: str, question: str, character_summary: str) -> Dict[str, Any]:
    """
    登場人物判定プロセス（固定: GPT-5.1）
    """
    prompt = f"""以下の文章は、ユーザーが今まで読んだ小説本文です。
----- 本文ここから -----
{story_text}
----- 本文ここまで -----

ユーザーから以下の質問がありました。
質問: {question}

この質問が「登場人物に関する質問」かどうかを判定してください。
- 登場人物の関係、行動、性格、背景などに関する質問なら「はい」
- それ以外なら「いいえ」

JSON形式で回答してください:
{{"is_character_question": "はい" or "いいえ", "reason": "理由"}}"""

    messages = [
        {"role": "system", "content": "あなたは質問を分類するアシスタントです。"},
        {"role": "user", "content": prompt}
    ]

    return openai_chat_timed(
        model=FIXED_MODELS["character_judgment"],
        messages=messages,
        log_label="登場人物判定",
        temperature=0.0
    )


def process_center_person(story_text: str, question: str, character_summary: str) -> Dict[str, Any]:
    """
    中心人物特定プロセス（固定: GPT-5.1）
    """
    prompt = f"""以下の文章は、ユーザーが今まで読んだ小説本文です。
----- 本文ここから -----
{story_text}
----- 本文ここまで -----

以下は登場人物の要約です:
{character_summary}

ユーザーの質問: {question}

この質問に答える上で中心となる人物を特定してください。
JSON形式で回答:
{{"center_person": "人物名", "reason": "理由"}}"""

    messages = [
        {"role": "system", "content": "あなたは登場人物を分析するアシスタントです。"},
        {"role": "user", "content": prompt}
    ]

    return openai_chat_timed(
        model=FIXED_MODELS["center_person"],
        messages=messages,
        log_label="中心人物特定",
        temperature=0.0
    )


def process_mermaid_generation(model: str, story_text: str, question: str,
                                center_person: str, character_summary: str) -> Dict[str, Any]:
    """
    Mermaid図生成プロセス（ラフ生成）
    """
    prompt = f"""以下の文章は、ユーザーが今まで読んだ小説本文です。
----- 本文ここから -----
{story_text}
----- 本文ここまで -----

以下は登場人物の要約です:
{character_summary}

中心人物: {center_person}
質問: {question}

この質問に答えるための人物関係図をMermaid記法で生成してください。
中心人物を中心に、関連する人物との関係を図示してください。

フォーマット:
```mermaid
graph TD
  ...
```"""

    messages = [
        {"role": "system", "content": "あなたはMermaid図を生成するアシスタントです。"},
        {"role": "user", "content": prompt}
    ]

    # gpt-5-miniはtemperatureをサポートしないため、モデルによって分岐
    kwargs = {"log_label": f"Mermaid生成({model})"}
    if "gpt-5-mini" not in model:
        kwargs["temperature"] = 0.3

    return openai_chat_timed(
        model=model,
        messages=messages,
        **kwargs
    )


def process_csv_conversion(model: str, mermaid_code: str) -> Dict[str, Any]:
    """
    CSV変換プロセス
    """
    prompt = f"""以下のMermaidコードをCSV形式に変換してください。

{mermaid_code}

CSV形式:
from,to,label"""

    messages = [
        {"role": "system", "content": "あなたはMermaidコードをCSVに変換するアシスタントです。"},
        {"role": "user", "content": prompt}
    ]

    # gpt-5-miniはtemperatureをサポートしないため、モデルによって分岐
    kwargs = {"log_label": f"CSV変換({model})"}
    if "gpt-5-mini" not in model:
        kwargs["temperature"] = 0.0

    return openai_chat_timed(
        model=model,
        messages=messages,
        **kwargs
    )


def process_answer_generation(model: str, story_text: str, question: str) -> Dict[str, Any]:
    """
    質問への回答生成プロセス
    """
    prompt = f"""以下はユーザーがこれまでに読んだ小説本文です。

----- 本文ここから -----
{story_text}
----- 本文ここまで -----

# 指示
この本文の内容を根拠にユーザーの質問に日本語で丁寧に答えてください。

質問: {question}"""

    messages = [
        {"role": "system", "content": "あなたは読んでいる小説について質問に答えるアシスタントです。"},
        {"role": "user", "content": prompt}
    ]

    # gpt-5-miniはtemperatureをサポートしないため、モデルによって分岐
    kwargs = {"log_label": f"回答生成({model})"}
    if "gpt-5-mini" not in model:
        kwargs["temperature"] = 0.7

    return openai_chat_timed(
        model=model,
        messages=messages,
        **kwargs
    )


# =================================================
#           テスト実行
# =================================================

def run_single_test(question_data: Dict, mermaid_model: str, answer_model: str,
                    story_text: str, character_summary: str, test_num: int = 0, total_tests: int = 0) -> Dict[str, Any]:
    """
    1つのテストケースを実行
    """
    question_id = question_data["id"]
    question = question_data["question"]

    progress_info = f"[{test_num}/{total_tests}]" if total_tests > 0 else ""
    logger.info(f"\n{'='*60}")
    logger.info(f"{progress_info} テスト開始: {question_id} - Mermaid/CSV={mermaid_model}, Answer={answer_model}")
    logger.info(f"質問: {question}")
    logger.info(f"{'='*60}")

    results = {
        "question_id": question_id,
        "question": question,
        "question_type": question_data["type"],
        "mermaid_model": mermaid_model,
        "answer_model": answer_model,
        "processes": {},
        "outputs": {},
        "total_time": 0,
        "timestamp": datetime.now().isoformat()
    }

    # 1. 登場人物判定（固定: GPT-5.1）
    judgment_result = process_character_judgment(story_text, question, character_summary)
    results["processes"]["character_judgment"] = {
        "model": FIXED_MODELS["character_judgment"],
        "time": judgment_result["time"],
        "tokens": judgment_result["tokens"]
    }
    results["outputs"]["character_judgment"] = judgment_result["content"]

    # 2. 中心人物特定（固定: GPT-5.1）
    center_result = process_center_person(story_text, question, character_summary)
    results["processes"]["center_person"] = {
        "model": FIXED_MODELS["center_person"],
        "time": center_result["time"],
        "tokens": center_result["tokens"]
    }
    results["outputs"]["center_person"] = center_result["content"]

    # 中心人物を抽出（簡易版）
    try:
        center_data = json.loads(center_result["content"])
        center_person = center_data.get("center_person", "不明")
    except:
        center_person = "不明"

    # 3. Mermaid生成
    mermaid_result = process_mermaid_generation(
        mermaid_model, story_text, question, center_person, character_summary
    )
    results["processes"]["mermaid_generation"] = {
        "model": mermaid_model,
        "time": mermaid_result["time"],
        "tokens": mermaid_result["tokens"]
    }
    results["outputs"]["mermaid_code"] = mermaid_result["content"]

    # 4. CSV変換
    csv_result = process_csv_conversion(mermaid_model, mermaid_result["content"])
    results["processes"]["csv_conversion"] = {
        "model": mermaid_model,
        "time": csv_result["time"],
        "tokens": csv_result["tokens"]
    }
    results["outputs"]["csv_data"] = csv_result["content"]

    # 5. 回答生成
    answer_result = process_answer_generation(answer_model, story_text, question)
    results["processes"]["answer_generation"] = {
        "model": answer_model,
        "time": answer_result["time"],
        "tokens": answer_result["tokens"]
    }
    results["outputs"]["answer"] = answer_result["content"]

    # 合計時間
    results["total_time"] = sum(p["time"] for p in results["processes"].values())

    # プロセス別の時間内訳を表示
    process_times = {
        "登場人物判定": results["processes"]["character_judgment"]["time"],
        "中心人物特定": results["processes"]["center_person"]["time"],
        "Mermaid生成": results["processes"]["mermaid_generation"]["time"],
        "CSV変換": results["processes"]["csv_conversion"]["time"],
        "回答生成": results["processes"]["answer_generation"]["time"]
    }

    logger.info(f"\n{'='*60}")
    logger.info(f"{progress_info} テスト完了: {question_id}")
    logger.info(f"合計時間: {results['total_time']:.2f}s")
    logger.info(f"内訳: " + " | ".join([f"{k}={v:.2f}s" for k, v in process_times.items()]))
    logger.info(f"{'='*60}\n")

    return results


def warmup_prompt_cache(story_text: str, character_summary: str):
    """
    プロンプトキャッシュをウォームアップ（zikken_11month_v7.pyと同じ処理）

    これにより、最初のテストから高速な応答が可能になる
    """
    logger.info("\n" + "=" * 80)
    logger.info("🔥 プロンプトキャッシュをウォームアップ中...")
    logger.info("=" * 80)

    try:
        # 1. 本文キャッシュを作成
        warmup_prompt_story = f"""
本文:
{story_text}

質問: 主人公について教えてください

要件:
- graph LR または graph TD で開始
- **主人公を中心**に、直接関わる主要人物のみを含める
- 登場人物は物語上重要な人物に限定する（5-10人程度）
- 関係性の表現：
  * 双方向の関係: <--> を使用（例: 友人、仲間、恋人など）
  * 一方向の関係: --> を使用（例: 上司→部下、師匠→弟子など）
  * 点線矢印 -.-> は補助的な関係に使用
- **重要**: 同じ2人の間の関係は最大2本まで（AからB、BからA）
- エッジには簡潔な日本語ラベルを付ける（5文字以内推奨）
- 必要に応じてsubgraphでグループ化（例: 勇者パーティー、魔王軍など）
- 主人公に直接関わらない人物間の関係は省略する

以上の質問と本文を基に、「主人公」を中心とした主要登場人物の関係図をMermaid形式で生成してください。
出力はMermaidコードのみ（説明不要）
"""

        logger.info("本文キャッシュを作成中...")
        _ = openai_chat_timed(
            "gpt-5.1",
            messages=[
                {"role": "system", "content": "Mermaid図を生成する専門家です。"},
                {"role": "user", "content": warmup_prompt_story}
            ],
            temperature=0.3,
            log_label="キャッシュウォームアップ（本文）"
        )

        # 2. 登場人物情報キャッシュを作成
        if character_summary:
            warmup_prompt_character = f"""
登場人物情報:
{character_summary}

---

質問: 主人公について教えてください

この質問の中心となる登場人物の名前を1つだけ答えてください。

要件:
- 登場人物情報に記載されている正確な人物名で回答
- 人物名のみを1行で出力（説明不要）

回答:
"""

            logger.info("登場人物情報キャッシュを作成中...")
            _ = openai_chat_timed(
                "gpt-5.1",
                messages=[
                    {"role": "system", "content": "質問の中心人物を特定します。"},
                    {"role": "user", "content": warmup_prompt_character}
                ],
                temperature=0,
                log_label="キャッシュウォームアップ（登場人物）"
            )

        logger.info("✅ プロンプトキャッシュのウォームアップが完了しました")
        logger.info("=" * 80 + "\n")

    except Exception as e:
        logger.warning(f"⚠️ キャッシュウォームアップ中にエラーが発生しましたが、テストを続行します: {e}")


def run_all_tests():
    """
    全てのテストケースを実行
    """
    logger.info("=" * 80)
    logger.info("モデル比較実験を開始します")
    logger.info("=" * 80)

    # 小説本文と登場人物要約を読み込み
    story_text = load_story_text()
    character_summary = load_character_summary()

    logger.info(f"小説本文: {len(story_text)} 文字")
    logger.info(f"登場人物要約: {len(character_summary)} 文字")

    # プロンプトキャッシュをウォームアップ
    warmup_prompt_cache(story_text, character_summary)

    # 全テスト結果を保存
    all_results = []

    # テスト実行（全ての組み合わせをテスト）
    # 実験の規模を考慮して、代表的な組み合わせのみテスト
    test_combinations = [
        # GPT-5.1 ベースライン
        ("gpt-5.1", "gpt-4.1"),
        # GPT-5-mini
        ("gpt-5-mini", "gpt-5-mini"),
        # GPT-4 系
        ("gpt-4.1", "gpt-4.1"),
        ("gpt-4o", "gpt-4o"),
        # Mini系
        ("gpt-4o-mini", "gpt-4o-mini"),
        # 混合
        ("gpt-5.1", "gpt-5-mini"),
        ("gpt-4.1", "gpt-5-mini"),
    ]

    total_tests = len(TEST_QUESTIONS) * len(test_combinations)
    current_test = 0

    # 開始時刻を記録
    start_time = time.time()

    for question_data in TEST_QUESTIONS:
        for mermaid_model, answer_model in test_combinations:
            current_test += 1

            # 進捗状況を計算
            progress_pct = (current_test / total_tests) * 100
            elapsed = time.time() - start_time
            if current_test > 1:
                avg_time = elapsed / (current_test - 1)
                remaining = avg_time * (total_tests - current_test)
                eta_str = f"残り約{remaining/60:.1f}分"
            else:
                eta_str = "計算中..."

            logger.info(f"\n{'='*80}")
            logger.info(f"📊 進捗: {current_test}/{total_tests} ({progress_pct:.1f}%) | 経過時間: {elapsed/60:.1f}分 | {eta_str}")
            logger.info(f"{'='*80}")

            try:
                result = run_single_test(
                    question_data=question_data,
                    mermaid_model=mermaid_model,
                    answer_model=answer_model,
                    story_text=story_text,
                    character_summary=character_summary,
                    test_num=current_test,
                    total_tests=total_tests
                )
                all_results.append(result)

                # 中間結果を保存（10テストごと）
                if current_test % 10 == 0 or current_test == total_tests:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    intermediate_file = f"model_comparison_intermediate_{timestamp}.json"
                    with open(intermediate_file, 'w', encoding='utf-8') as f:
                        json.dump(all_results, f, ensure_ascii=False, indent=2)
                    logger.info(f"💾 中間結果を保存しました: {intermediate_file}")

                # 少し待機（API rate limit対策）
                time.sleep(1)

            except Exception as e:
                logger.error(f"❌ テスト失敗: {question_data['id']}, {mermaid_model}, {answer_model}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                continue

    # 最終結果のサマリー
    total_elapsed = time.time() - start_time
    successful_tests = len(all_results)
    logger.info(f"\n{'='*80}")
    logger.info(f"✅ 全テスト完了!")
    logger.info(f"成功: {successful_tests}/{total_tests} テスト")
    logger.info(f"総実行時間: {total_elapsed/60:.1f}分")
    logger.info(f"{'='*80}\n")

    return all_results


def save_results_to_csv(results: List[Dict], output_file: str = "model_comparison_results.csv"):
    """
    結果をCSVファイルに保存
    """
    if not results:
        logger.warning("保存する結果がありません")
        return

    # CSV出力
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)

        # ヘッダー
        headers = [
            "質問ID", "質問", "質問タイプ",
            "Mermaid/CSVモデル", "回答モデル",
            "登場人物判定(s)", "登場人物判定(tokens)",
            "中心人物特定(s)", "中心人物特定(tokens)",
            "Mermaid生成(s)", "Mermaid生成(tokens)",
            "CSV変換(s)", "CSV変換(tokens)",
            "回答生成(s)", "回答生成(tokens)",
            "合計時間(s)", "合計トークン数",
            "タイムスタンプ"
        ]
        writer.writerow(headers)

        # データ行
        for r in results:
            total_tokens = sum(p["tokens"]["total"] for p in r["processes"].values())

            row = [
                r["question_id"],
                r["question"],
                r["question_type"],
                r["mermaid_model"],
                r["answer_model"],
                f"{r['processes']['character_judgment']['time']:.2f}",
                r['processes']['character_judgment']['tokens']['total'],
                f"{r['processes']['center_person']['time']:.2f}",
                r['processes']['center_person']['tokens']['total'],
                f"{r['processes']['mermaid_generation']['time']:.2f}",
                r['processes']['mermaid_generation']['tokens']['total'],
                f"{r['processes']['csv_conversion']['time']:.2f}",
                r['processes']['csv_conversion']['tokens']['total'],
                f"{r['processes']['answer_generation']['time']:.2f}",
                r['processes']['answer_generation']['tokens']['total'],
                f"{r['total_time']:.2f}",
                total_tokens,
                r["timestamp"]
            ]
            writer.writerow(row)

    logger.info(f"✓ 結果をCSVに保存しました: {output_file}")


def save_detailed_results_to_json(results: List[Dict], output_file: str = "model_comparison_detailed.json"):
    """
    詳細な結果（生成内容含む）をJSONファイルに保存
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"✓ 詳細結果をJSONに保存しました: {output_file}")


# =================================================
#           メイン実行
# =================================================

if __name__ == "__main__":
    logger.info("モデル比較実験スクリプトを開始します")
    logger.info(f"テスト質問数: {len(TEST_QUESTIONS)}")
    logger.info(f"Mermaid/CSVテストモデル: {TEST_MODELS['mermaid_csv']}")
    logger.info(f"回答生成テストモデル: {TEST_MODELS['answer_generation']}")

    # テスト実行
    results = run_all_tests()

    # 結果保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"model_comparison_results_{timestamp}.csv"
    json_file = f"model_comparison_detailed_{timestamp}.json"

    save_results_to_csv(results, csv_file)
    save_detailed_results_to_json(results, json_file)

    logger.info("=" * 80)
    logger.info("全テスト完了!")
    logger.info(f"総テスト数: {len(results)}")
    logger.info(f"CSV出力: {csv_file}")
    logger.info(f"JSON出力: {json_file}")
    logger.info("=" * 80)
