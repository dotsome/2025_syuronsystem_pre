#!/usr/bin/env python3
"""
Prompt Cachingが実際に効いているか確認するテストスクリプト
"""
import os
import time
from dotenv import load_dotenv
import openai
import json

load_dotenv()
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 長いプロンプトを用意（キャッシュ効果を確認するため）
with open("beast_text.json", "r", encoding="utf-8") as f:
    story_data = json.load(f)

story_text = "\n\n".join([
    f"【{sec['section']}章】 {sec['title']}\n\n{sec['text']}"
    for sec in story_data[:31]  # 31ページ
])

print("=" * 80)
print("Prompt Caching テスト")
print("=" * 80)
print(f"本文サイズ: {len(story_text)} 文字\n")

# テストするモデル
test_models = ["gpt-4o", "gpt-4o-mini", "gpt-5.1", "gpt-4.1"]

for model in test_models:
    print(f"\n{'=' * 80}")
    print(f"モデル: {model}")
    print(f"{'=' * 80}")

    # 同じプロンプトで2回呼び出し
    for attempt in [1, 2]:
        print(f"\n[{attempt}回目]")

        prompt = f"""本文:
{story_text}

質問: レインって誰ですか？

上記の質問に簡潔に答えてください。"""

        try:
            start = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "質問に答えるアシスタント"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            elapsed = time.time() - start

            usage = response.usage

            print(f"  時間: {elapsed:.2f}s")
            print(f"  Prompt tokens: {usage.prompt_tokens}")
            print(f"  Completion tokens: {usage.completion_tokens}")
            print(f"  Total tokens: {usage.total_tokens}")

            # Prompt Caching情報を確認
            if hasattr(usage, 'prompt_tokens_details'):
                details = usage.prompt_tokens_details
                if hasattr(details, 'cached_tokens'):
                    print(f"  ✅ Cached tokens: {details.cached_tokens}")
                else:
                    print(f"  ℹ️  prompt_tokens_details にcached_tokensフィールドなし")
            else:
                print(f"  ℹ️  usageにprompt_tokens_detailsフィールドなし")

            # 少し待つ
            if attempt == 1:
                time.sleep(2)

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            break

print("\n" + "=" * 80)
print("テスト完了")
print("=" * 80)
print("\n💡 結果の見方:")
print("  - 2回目のcached_tokensが0より大きい → Prompt Caching有効")
print("  - 2回目もprompt_tokensが同じ → Prompt Caching無効")
print("  - prompt_tokens_detailsフィールドがない → モデルが非対応")
