#!/usr/bin/env python3
"""
失敗したMermaidファイルを修正して画像に変換するスクリプト
"""

from pathlib import Path
import subprocess

def write_and_convert(filename: str, content: str) -> bool:
    """Mermaidファイルを書き込んで画像に変換"""
    mermaid_dir = Path(__file__).parent / "mermaid_outputs"
    mmd_file = mermaid_dir / filename
    png_file = mmd_file.with_suffix('.png')

    # 修正版を書き込み
    with open(mmd_file, 'w', encoding='utf-8') as f:
        f.write(content)

    # 画像に変換
    try:
        subprocess.run(
            ['mmdc', '-i', str(mmd_file), '-o', str(png_file),
             '-b', 'transparent', '-w', '800', '-H', '600'],
            check=True, capture_output=True, text=True
        )
        print(f"✅ {filename} → {png_file.name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {filename} 変換失敗")
        print(f"   エラー: {e.stderr}")
        return False

# Q2_gpt-4.1_gpt-4.1.mmd - <br/>タグと複雑な構文を簡略化
content1 = """graph TD
    R["レイン・シュラウド"]
    K["カナデ"]
    T["タニア"]
    S["ソラ"]
    L["ルナ"]
    A["アリオス"]

    R -->|主従契約・信頼| K
    K -->|深い信頼| R
    R -->|主従契約・信頼| T
    T -->|信頼・好意| R
    R -->|主従契約| S
    S -->|信頼| R
    R -->|主従契約| L
    L -->|信頼| R
    K ---|仲間| T
    R ---|元仲間| A
    K ---|敵意| A
    T ---|敵意| A
"""

# Q2_gpt-4o-mini_gpt-4o-mini.mmd - ノード定義なし
content2 = """graph TD
    RAIN["レイン・シュラウド"]
    KANADE["カナデ"]
    TANIA["タニア"]

    RAIN -->|仲間| KANADE
    RAIN -->|仲間| TANIA
    KANADE -->|信頼| RAIN
    TANIA -->|信頼| RAIN
    KANADE -->|友人| TANIA
    TANIA -->|友人| KANADE
"""

# Q2_gpt-4.1_gpt-5-mini.mmd - 複雑すぎる構文
content3 = """graph TD
    R["レイン・シュラウド"]
    K["カナデ"]
    T["タニア"]
    S["ソラ"]
    L["ルナ"]

    R -->|主従契約・信頼| K
    K -->|深い信頼・好意| R
    R -->|主従契約・信頼| T
    T -->|ツンデレ的信頼| R
    R -->|主従契約| S
    S -->|深い信頼| R
    R -->|主従契約| L
    L -->|信頼| R
    K ---|仲間| T
    K ---|仲間| S
    K ---|仲間| L
    T ---|仲間| S
    T ---|仲間| L
"""

# Q3_gpt-4o-mini_gpt-4o-mini.mmd - ノード定義なし
content4 = """graph TD
    RAIN["レイン・シュラウド"]
    ARIOS["アリオス"]
    KANADE["カナデ"]
    TANIA["タニア"]

    RAIN -->|元仲間| ARIOS
    ARIOS -->|追放| RAIN
    KANADE -->|敵対| ARIOS
    TANIA -->|敵対| ARIOS
    KANADE -->|仲間| RAIN
    TANIA -->|仲間| RAIN
"""

# Q4_gpt-5-mini_gpt-5-mini.mmd - 改行コードと複雑な構文
content5 = """graph TD
    TANIA["タニア"]
    LEAN["リーン"]
    RAIN["レイン"]
    KANADE["カナデ"]
    ARIOS["アリオス"]

    TANIA -->|契約・仲間| RAIN
    TANIA -->|共闘| KANADE
    TANIA -->|対立・敵対| LEAN
    TANIA -->|魔法打ち消し| LEAN
    LEAN -->|勇者PT| ARIOS
"""

# Q4_gpt-4o_gpt-4o.mmd - ノード定義なし
content6 = """graph TD
    TANIA["タニア"]
    RAIN["レイン・シュラウド"]
    KANADE["カナデ"]
    LEAN["リーン"]
    ARIOS["アリオス"]
    MINA["ミナ"]
    AGGAS["アッガス"]

    TANIA -->|仲間| RAIN
    TANIA -->|仲間| KANADE
    TANIA -->|敵対| LEAN
    TANIA -->|敵対| ARIOS
    RAIN -->|元仲間| LEAN
    RAIN -->|元仲間| ARIOS
    KANADE -->|仲間| RAIN
    LEAN -->|仲間| ARIOS
    LEAN -->|仲間| MINA
"""

if __name__ == "__main__":
    print("🔧 失敗したMermaidファイルを修正して変換します\n")

    success_count = 0
    files = [
        ("Q2_gpt-4.1_gpt-4.1.mmd", content1),
        ("Q2_gpt-4o-mini_gpt-4o-mini.mmd", content2),
        ("Q2_gpt-4.1_gpt-5-mini.mmd", content3),
        ("Q3_gpt-4o-mini_gpt-4o-mini.mmd", content4),
        ("Q4_gpt-5-mini_gpt-5-mini.mmd", content5),
        ("Q4_gpt-4o_gpt-4o.mmd", content6),
    ]

    for filename, content in files:
        if write_and_convert(filename, content):
            success_count += 1

    print(f"\n✨ 完了: {success_count}/{len(files)} ファイルを修正・変換しました")
