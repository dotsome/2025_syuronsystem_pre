"""
忘却テキスト生成プログラム

久しぶりに読書を再開する想定で、忘却を含んだ要約を生成します。
- 複数の文字数パターン（2000, 2500文字）
- 各パターンで3つのバリエーション
- shadow_text.json のみに対応
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# .envファイルから環境変数を読み込み（既存の環境変数を上書き）
load_dotenv(override=True)

# OpenAI APIキー設定
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def load_novel(novel_file: str, max_chapters: int = 30) -> str:
    """
    小説ファイルを読み込み、指定章数までの本文を結合

    Args:
        novel_file: 小説ファイル名
        max_chapters: 読み込む最大章数（デフォルト: 30）

    Returns:
        結合された本文
    """
    with open(novel_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 指定章数まで取得
    chapters = data[:max_chapters]

    # 本文を結合
    full_text = "\n\n".join([
        f"【{ch['section']}章】 {ch['title']}\n\n{ch['text']}"
        for ch in chapters
    ])

    return full_text


def generate_forgetting_text(novel_text: str, char_limit: int, model: str = "gpt-5.1") -> str:
    """
    忘却テキストを生成

    Args:
        novel_text: 小説の本文
        char_limit: 文字数制限
        model: 使用するモデル（デフォルト: gpt-5.1）

    Returns:
        生成された忘却テキスト
    """
    input_text = f"""この小説を以下の形で要約してください。

【要約の条件】
・久しぶりに読んだ想定
・主人公の存在は覚えている
・主人公周辺の人物もなんとなく覚えている
・ただ詳細に何があったのかは覚えていない
・勘違いや混乱・欠落が時々存在する
・物語の内容を追う形であらすじを作成する
・忘却している風のロールプレイのような文章は不要
・あらすじ形式で出力する（箇条書きにしない）

【重要：文字数の指定】
・必ず{char_limit}文字前後（±200文字程度）で出力してください
・最低でも{char_limit - 500}文字以上は必須です
・覚えている範囲で、できるだけ詳しく各章やエピソードの内容を書いてください
・短くまとめすぎないように注意してください

【小説本文】
{novel_text}

【忘却を含んだ要約】
"""

    result = client.responses.create(
        model=model,
        input=input_text,
        reasoning={"effort": "medium"},
        text={"verbosity": "high"},
    )

    return result.output_text.strip()


def save_forgetting_text(novel_name: str, char_limit: int, pattern_num: int, text: str):
    """
    忘却テキストをファイルに保存

    Args:
        novel_name: 小説名（"beast" or "shadow"）
        char_limit: 文字数制限
        pattern_num: パターン番号（1-3）
        text: 保存するテキスト
    """
    output_dir = Path("forgetting_texts") / novel_name
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_dir / f"{char_limit}chars_pattern{pattern_num}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"✅ 保存完了: {filename} ({len(text)}文字)")


def main():
    """メイン処理"""
    # 設定: 各小説の読者が読む推奨章の一つ前までを対象とする
    novels = {
        "shadow": {
            "file": "shadow_text.json",
            "max_chapters": 30  # 31-32章を読むので、30章までのあらすじ
        },
        "sangoku_2": {
            "file": "sangoku_2_text.json",
            "max_chapters": 56  # 57-58章を読むので、56章までのあらすじ
        },
        "ranpo": {
            "file": "ranpo_text_ruby.json",
            "max_chapters": 10  # 11-12章を読むので、10章までのあらすじ
        },
        "texhnical_area": {
            "file": "texhnical_area_text.json",
            "max_chapters": 43  # 44-45章を読むので、43章までのあらすじ
        },
        "online_utyu": {
            "file": "online_utyu_text.json",
            "max_chapters": 22  # 23-24章を読むので、22章までのあらすじ
        }
    }

    char_limits = [500]  # 500文字パターンのみ生成
    patterns_per_limit = 1  # 1つのみ生成
    model = "gpt-5.1"  # GPT-5.1を使用

    print("🚀 忘却テキスト生成を開始します")
    print(f"モデル: {model}")
    print(f"文字数パターン: {char_limits}")
    print(f"各パターンの生成数: {patterns_per_limit}")
    print()

    for novel_name, novel_config in novels.items():
        print(f"📖 {novel_name.upper()} の処理を開始")

        # 小説本文を読み込み（各小説の推奨章の一つ前まで）
        novel_text = load_novel(novel_config["file"], max_chapters=novel_config["max_chapters"])
        print(f"  本文読み込み完了: {novel_config['max_chapters']}章まで, {len(novel_text):,}文字")

        for char_limit in char_limits:
            print(f"\n  📝 {char_limit}文字パターン:")

            for pattern_num in range(1, patterns_per_limit + 1):
                print(f"    パターン{pattern_num}を生成中...", end=" ")

                try:
                    # 忘却テキスト生成
                    forgetting_text = generate_forgetting_text(
                        novel_text=novel_text,
                        char_limit=char_limit,
                        model=model
                    )

                    # 保存
                    save_forgetting_text(
                        novel_name=novel_name,
                        char_limit=char_limit,
                        pattern_num=pattern_num,
                        text=forgetting_text
                    )

                except Exception as e:
                    print(f"❌ エラー: {e}")

        print(f"\n✅ {novel_name.upper()} の処理完了\n")

    print("🎉 全ての忘却テキスト生成が完了しました")
    print(f"📁 保存先: forgetting_texts/")


if __name__ == "__main__":
    main()
