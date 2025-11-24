#!/usr/bin/env python3
"""
失敗したMermaidファイルを手動で修正して再変換
"""
import subprocess
from pathlib import Path

mermaid_dir = Path("mermaid_outputs")
image_dir = Path("mermaid_images")
image_dir.mkdir(exist_ok=True)

def convert_to_image(content: str, output_file: Path) -> bool:
    """修正済みMermaidコードを画像に変換"""
    temp_file = Path("temp_mermaid.mmd")

    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(content)

    cmd = [
        'mmdc',
        '-i', str(temp_file),
        '-o', str(output_file),
        '-b', 'transparent',
        '-w', '800',
        '-H', '600'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        temp_file.unlink()

        if result.returncode == 0 and output_file.exists():
            return True
        else:
            print(f"   エラー: {result.stderr[:200]}")
            return False
    except Exception as e:
        if temp_file.exists():
            temp_file.unlink()
        print(f"   例外: {e}")
        return False

print("=" * 80)
print("失敗したMermaidファイルを手動修正して再変換します")
print("=" * 80 + "\n")

# 各ファイルを個別に修正

# 1. Q2_gpt-4.1_gpt-4.1.mmd - スタイル定義を削除して簡略化
print("1. Q2_gpt-4.1_gpt-4.1.mmd を修正中...")
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
if convert_to_image(content1, image_dir / "Q2_gpt-4.1_gpt-4.1.png"):
    print("   ✅ 成功")
    with open(mermaid_dir / "Q2_gpt-4.1_gpt-4.1.mmd", 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{content1}```")
else:
    print("   ❌ 失敗")

# 2. Q2_gpt-4o-mini_gpt-4o-mini.mmd - シンプルなID形式に変更
print("2. Q2_gpt-4o-mini_gpt-4o-mini.mmd を修正中...")
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
if convert_to_image(content2, image_dir / "Q2_gpt-4o-mini_gpt-4o-mini.png"):
    print("   ✅ 成功")
    with open(mermaid_dir / "Q2_gpt-4o-mini_gpt-4o-mini.mmd", 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{content2}```")
else:
    print("   ❌ 失敗")

# 3. Q2_gpt-4.1_gpt-5-mini.mmd - 複雑なラベルを簡略化
print("3. Q2_gpt-4.1_gpt-5-mini.mmd を修正中...")
content3 = """graph TD
    R["レイン"]
    K["カナデ"]
    T["タニア"]
    S["ソラ"]
    L["ルナ"]

    R -->|主従契約| K
    R -->|主従契約| T
    R -->|主従契約| S
    R -->|主従契約| L
    K -->|信頼・好意| R
    T -->|信頼・好意| R
    K ---|最強種同士| T
"""
if convert_to_image(content3, image_dir / "Q2_gpt-4.1_gpt-5-mini.png"):
    print("   ✅ 成功")
    with open(mermaid_dir / "Q2_gpt-4.1_gpt-5-mini.mmd", 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{content3}```")
else:
    print("   ❌ 失敗")

# 4. Q3_gpt-4o-mini_gpt-4o-mini.mmd
print("4. Q3_gpt-4o-mini_gpt-4o-mini.mmd を修正中...")
content4 = """graph TD
    RAIN["レイン・シュラウド"]
    ARIOS["アリオス"]
    KANADE["カナデ"]
    TANIA["タニア"]
    AGGAS["アッガス"]
    LEAN["リーン"]

    RAIN -->|元仲間| ARIOS
    RAIN -->|仲間| KANADE
    RAIN -->|仲間| TANIA
    ARIOS -->|リーダー| AGGAS
    ARIOS -->|リーダー| LEAN
    KANADE -->|敵対| ARIOS
    TANIA -->|敵対| LEAN
"""
if convert_to_image(content4, image_dir / "Q3_gpt-4o-mini_gpt-4o-mini.png"):
    print("   ✅ 成功")
    with open(mermaid_dir / "Q3_gpt-4o-mini_gpt-4o-mini.mmd", 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{content4}```")
else:
    print("   ❌ 失敗")

# 5. Q4_gpt-5-mini_gpt-5-mini.mmd - 複雑な定義を簡略化
print("5. Q4_gpt-5-mini_gpt-5-mini.mmd を修正中...")
content5 = """graph TD
    TANIA["タニア（竜族）"]
    LEAN["リーン（魔法使い）"]
    RAIN["レイン（主人公）"]
    KANADE["カナデ（猫霊族）"]
    ARIOS["アリオス（勇者）"]

    TANIA -->|契約・仲間| RAIN
    TANIA -->|共闘| KANADE
    TANIA -->|対立・敵対| LEAN
    TANIA -->|魔法打ち消し| LEAN
    LEAN -->|勇者PT| ARIOS
"""
if convert_to_image(content5, image_dir / "Q4_gpt-5-mini_gpt-5-mini.png"):
    print("   ✅ 成功")
    with open(mermaid_dir / "Q4_gpt-5-mini_gpt-5-mini.mmd", 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{content5}```")
else:
    print("   ❌ 失敗")

# 6. Q4_gpt-4o_gpt-4o.mmd
print("6. Q4_gpt-4o_gpt-4o.mmd を修正中...")
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
if convert_to_image(content6, image_dir / "Q4_gpt-4o_gpt-4o.png"):
    print("   ✅ 成功")
    with open(mermaid_dir / "Q4_gpt-4o_gpt-4o.mmd", 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{content6}```")
else:
    print("   ❌ 失敗")

print("\n✨ 完了！修正版の画像を確認してください")
