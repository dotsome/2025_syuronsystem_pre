"""
Mermaid図生成のモデル別パフォーマンス検証スクリプト

使用方法:
    python model_benchmark.py

出力:
    - benchmark_results.csv: 各モデルの処理時間とトークン使用量
    - benchmark_details.txt: 詳細なログ
"""

import os
import json
import time
import csv
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import openai

# 環境変数読み込み
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ OPENAI_API_KEY が設定されていません")
    exit(1)

client = openai.OpenAI(api_key=api_key)

# ===============================================
#  テストデータの読み込み
# ===============================================
def load_test_data(filename="beast_text.json"):
    """小説データを読み込む"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            story_sections = json.load(f)

        # 全章のテキストを結合
        story_text = "\n\n".join([
            f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
            for sec in story_sections
        ])

        return story_text
    except FileNotFoundError:
        print(f"❌ {filename} が見つかりません")
        exit(1)

# ===============================================
#  Mermaid図生成関数
# ===============================================
def generate_mermaid_rough(model: str, question: str, story_text: str, main_focus: str = "タニア") -> dict:
    """
    指定されたモデルでMermaid図を生成し、処理時間とトークン数を計測

    Returns:
        dict: {
            'model': モデル名,
            'time': 処理時間(秒),
            'prompt_tokens': プロンプトトークン数,
            'completion_tokens': 完了トークン数,
            'total_tokens': 合計トークン数,
            'mermaid_code': 生成されたMermaidコード,
            'error': エラーメッセージ (エラー時のみ)
        }
    """
    prompt = f"""
以下の質問と本文を基に、「{main_focus}」を中心とした主要登場人物の関係図をMermaid形式で生成してください。

質問: {question}

本文:
{story_text}

要件:
- graph LR または graph TD で開始
- **{main_focus}を中心**に、直接関わる主要人物のみを含める
- 登場人物は物語上重要な人物に限定する（5-10人程度）
- 関係性の表現：
  * 双方向の関係: <--> を使用（例: 友人、仲間、恋人など）
  * 一方向の関係: --> を使用（例: 上司→部下、師匠→弟子など）
  * 点線矢印 -.-> は補助的な関係に使用
- **重要**: 同じ2人の間の関係は最大2本まで（AからB、BからA）
- エッジには簡潔な日本語ラベルを付ける（5文字以内推奨）
- 必要に応じてsubgraphでグループ化（例: 勇者パーティー、魔王軍など）
- {main_focus}に直接関わらない人物間の関係は省略する

出力はMermaidコードのみ（説明不要）
"""

    result = {
        'model': model,
        'time': 0,
        'prompt_tokens': 0,
        'completion_tokens': 0,
        'total_tokens': 0,
        'mermaid_code': '',
        'error': None
    }

    try:
        start_time = time.time()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Mermaid図を生成する専門家です。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        elapsed = time.time() - start_time

        # トークン使用量を取得
        usage = response.usage
        result['time'] = elapsed
        result['prompt_tokens'] = usage.prompt_tokens if usage else 0
        result['completion_tokens'] = usage.completion_tokens if usage else 0
        result['total_tokens'] = usage.total_tokens if usage else 0

        # Mermaidコードを取得
        mermaid_code = response.choices[0].message.content.strip()
        mermaid_code = mermaid_code.replace('```mermaid', '').replace('```', '').strip()
        result['mermaid_code'] = mermaid_code

        print(f"✅ {model}: {elapsed:.2f}秒, {result['total_tokens']} tokens")

    except Exception as e:
        result['error'] = str(e)
        print(f"❌ {model}: エラー - {e}")

    return result

# ===============================================
#  ベンチマーク実行
# ===============================================
def run_benchmark():
    """複数のモデルでベンチマークを実行（各モデル5回）"""

    print("=" * 60)
    print("Mermaid図生成 モデル別ベンチマーク（各モデル5回実行）")
    print("=" * 60)
    print()

    # テストデータ読み込み
    print("📖 テストデータを読み込み中...")
    story_text = load_test_data()
    question = "カナデって誰ですか？"
    main_focus = "カナデ"

    print(f"   - 本文文字数: {len(story_text):,} 文字")
    print(f"   - 質問: {question}")
    print(f"   - 中心人物: {main_focus}")
    print()

    # テスト対象のモデル
    models_to_test = [
        "gpt-4o-mini",      # 最も高速・低コスト
        "gpt-4o",           # バランス型
        "gpt-4.1",          # 現在使用中（比較用）
        "o1-mini",          # 推論特化型（小）
        "o3-mini",          # 推論特化型（最新）
    ]

    # 各モデルを5回実行
    num_runs = 5
    results = []

    print(f"🧪 各モデルで{num_runs}回ずつMermaid図を生成中...\n")

    total_tests = len(models_to_test) * num_runs
    current_test = 0

    for model in models_to_test:
        print(f"\n{'=' * 60}")
        print(f"モデル: {model}")
        print(f"{'=' * 60}")

        for run in range(1, num_runs + 1):
            current_test += 1
            print(f"  [{current_test}/{total_tests}] {model} - 実行 {run}/{num_runs}...")

            result = generate_mermaid_rough(
                model=model,
                question=question,
                story_text=story_text,
                main_focus=main_focus
            )

            # 実行回数を記録
            result['run'] = run
            results.append(result)

            # API制限を考慮して少し待機
            if current_test < total_tests:
                time.sleep(1)

    # 結果をCSVに保存
    save_results_to_csv(results)

    # 詳細をテキストファイルに保存
    save_results_to_text(results, story_text, question)

    # サマリー表示
    print_summary(results)

# ===============================================
#  結果の保存
# ===============================================
def save_results_to_csv(results):
    """結果をCSVファイルに保存"""
    output_file = "benchmark_results.csv"

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # ヘッダー
        writer.writerow([
            "Model",
            "Run",
            "Time (sec)",
            "Prompt Tokens",
            "Completion Tokens",
            "Total Tokens",
            "Success",
            "Error"
        ])

        # データ
        for r in results:
            writer.writerow([
                r['model'],
                r.get('run', 1),
                f"{r['time']:.2f}",
                r['prompt_tokens'],
                r['completion_tokens'],
                r['total_tokens'],
                "OK" if r['error'] is None else "FAILED",
                r['error'] if r['error'] else ""
            ])

    print(f"💾 結果を {output_file} に保存しました")

def save_results_to_text(results, story_text, question):
    """詳細結果をテキストファイルに保存"""
    output_file = "benchmark_details.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("Mermaid図生成 モデル別ベンチマーク 詳細結果\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"質問: {question}\n")
        f.write(f"本文文字数: {len(story_text):,} 文字\n\n")

        for i, r in enumerate(results, 1):
            f.write(f"\n{'=' * 80}\n")
            f.write(f"[{i}] {r['model']}\n")
            f.write(f"{'=' * 80}\n\n")

            if r['error']:
                f.write(f"❌ エラー: {r['error']}\n")
            else:
                f.write(f"処理時間: {r['time']:.2f} 秒\n")
                f.write(f"プロンプトトークン: {r['prompt_tokens']:,}\n")
                f.write(f"完了トークン: {r['completion_tokens']:,}\n")
                f.write(f"合計トークン: {r['total_tokens']:,}\n\n")

                f.write("生成されたMermaidコード:\n")
                f.write("-" * 80 + "\n")
                f.write(r['mermaid_code'] + "\n")
                f.write("-" * 80 + "\n")

    print(f"📄 詳細を {output_file} に保存しました")

# ===============================================
#  サマリー表示
# ===============================================
def print_summary(results):
    """結果のサマリーを表示（5回実行の平均値で比較）"""
    import statistics

    print()
    print("=" * 90)
    print("📊 ベンチマーク結果サマリー（各モデル5回実行の統計）")
    print("=" * 90)
    print()

    # モデルごとに結果を集計
    model_stats = {}
    for r in results:
        if r['error'] is not None:
            continue

        model = r['model']
        if model not in model_stats:
            model_stats[model] = {
                'times': [],
                'tokens': []
            }

        model_stats[model]['times'].append(r['time'])
        model_stats[model]['tokens'].append(r['total_tokens'])

    if not model_stats:
        print("❌ すべてのモデルでエラーが発生しました")
        return

    # 各モデルの統計を計算
    summary = []
    for model, stats in model_stats.items():
        if len(stats['times']) > 0:
            summary.append({
                'model': model,
                'avg_time': statistics.mean(stats['times']),
                'min_time': min(stats['times']),
                'max_time': max(stats['times']),
                'std_time': statistics.stdev(stats['times']) if len(stats['times']) > 1 else 0,
                'avg_tokens': statistics.mean(stats['tokens']),
                'num_runs': len(stats['times'])
            })

    # 平均時間でソート
    summary.sort(key=lambda x: x['avg_time'])

    # 最速のモデルを基準に相対速度を計算
    fastest_avg = summary[0]['avg_time']

    print(f"{'順位':<4} {'モデル':<15} {'平均時間':<12} {'最小-最大':<20} {'標準偏差':<10} {'相対速度':<10}")
    print("-" * 90)

    for i, s in enumerate(summary, 1):
        relative_speed = s['avg_time'] / fastest_avg
        print(f"{i:<4} {s['model']:<15} {s['avg_time']:>10.2f}s  "
              f"{s['min_time']:>6.2f}s - {s['max_time']:>6.2f}s  "
              f"±{s['std_time']:>6.2f}s  {relative_speed:>8.2f}x")

    print()

    # 失敗したモデル
    failed_models = set()
    for r in results:
        if r['error'] is not None:
            failed_models.add((r['model'], r['error']))

    if failed_models:
        print("⚠️  エラーが発生したモデル:")
        for model, error in failed_models:
            print(f"   - {model}: {error}")
        print()

    # 推奨事項
    print("💡 推奨事項:")
    if summary:
        fastest = summary[0]
        print(f"   - 最速（平均）: {fastest['model']} ({fastest['avg_time']:.2f}秒)")

        # gpt-4.1との比較
        gpt41_stats = next((s for s in summary if s['model'] == 'gpt-4.1'), None)
        if gpt41_stats:
            speedup = gpt41_stats['avg_time'] / fastest['avg_time']
            time_saved = gpt41_stats['avg_time'] - fastest['avg_time']
            print(f"   - gpt-4.1と比較して {speedup:.2f}x 高速化")
            print(f"   - 1回あたりの時間短縮: {time_saved:.2f}秒")
            print(f"   - 100回実行で約 {time_saved * 100 / 60:.1f}分 の短縮")

    print()

# ===============================================
#  メイン処理
# ===============================================
if __name__ == "__main__":
    try:
        run_benchmark()
        print("✅ ベンチマーク完了!")
        print()
        print("次のファイルを確認してください:")
        print("  - benchmark_results.csv (CSV形式の結果)")
        print("  - benchmark_details.txt (詳細なログ)")

    except KeyboardInterrupt:
        print("\n\n⚠️  ユーザーによって中断されました")
    except Exception as e:
        print(f"\n\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
