#!/usr/bin/env python3
"""
失敗したMermaidファイルを修正して再変換
"""
import subprocess
from pathlib import Path

# 失敗したファイルのリスト
failed_files = [
    "Q2_gpt-4.1_gpt-4.1.mmd",
    "Q2_gpt-4o-mini_gpt-4o-mini.mmd",
    "Q2_gpt-4.1_gpt-5-mini.mmd",
    "Q3_gpt-4o-mini_gpt-4o-mini.mmd",
    "Q4_gpt-5-mini_gpt-5-mini.mmd",
    "Q4_gpt-4o_gpt-4o.mmd"
]

mermaid_dir = Path("mermaid_outputs")
image_dir = Path("mermaid_images")
image_dir.mkdir(exist_ok=True)

def fix_and_convert(mermaid_file: Path) -> bool:
    """Mermaidファイルを修正して画像に変換"""

    # ファイルを読み込み
    with open(mermaid_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # ```mermaid と最初の ``` の間だけを抽出
    if '```mermaid' in content:
        content = content.split('```mermaid', 1)[1]
        if '```' in content:
            content = content.split('```', 1)[0]

    content = content.lstrip('\n')

    # 問題のあるパターンを修正
    # 1. <br/> を改行に変換（Mermaidでは\nを使う）
    content = content.replace('<br/>', '\\n').replace('<br>', '\\n')

    # 2. 裸の日本語ノード名を引用符で囲む
    # 例: graph TD の直後の行でノード定義されていないノード名
    lines = content.split('\n')
    fixed_lines = []
    in_graph = False

    for line in lines:
        if line.strip().startswith('graph '):
            in_graph = True
            fixed_lines.append(line)
            continue

        # ノード定義されていない裸の日本語を検出して修正
        # パターン1: "  日本語 -->|..." のような裸のノード名
        if in_graph and '--' in line:
            # 行頭の空白の後、括弧や引用符なしの日本語を検出
            import re
            # スペース + 日本語文字列 + スペース + 矢印
            # これをスペース + ["日本語文字列"] + スペース + 矢印に変換
            if re.search(r'^\s+([ぁ-んァ-ヶー一-龠々・]+)\s+--', line):
                line = re.sub(r'^(\s+)([ぁ-んァ-ヶー一-龠々・]+)(\s+--)', r'\1["\2"]\3', line)

            # 矢印の後の日本語ノード名
            if re.search(r'-->\s*([ぁ-んァ-ヶー一-龠々・]+)\s*$', line):
                line = re.sub(r'(-->)\s*([ぁ-んァ-ヶー一-龠々・]+)\s*$', r'\1 ["\2"]', line)

            # |ラベル| の後の日本語ノード名
            if re.search(r'\|\s*([ぁ-んァ-ヶー一-龠々・]+)\s*$', line):
                line = re.sub(r'(\|[^|]+\|)\s*([ぁ-んァ-ヶー一-龠々・]+)\s*$', r'\1 ["\2"]', line)

        fixed_lines.append(line)

    content = '\n'.join(fixed_lines)

    # 修正版を一時ファイルに保存
    fixed_file = mermaid_dir / f"fixed_{mermaid_file.name}"
    with open(fixed_file, 'w', encoding='utf-8') as f:
        f.write(content)

    # 画像に変換
    output_file = image_dir / mermaid_file.with_suffix('.png').name

    cmd = [
        'mmdc',
        '-i', str(fixed_file),
        '-o', str(output_file),
        '-b', 'transparent',
        '-w', '800',
        '-H', '600'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and output_file.exists():
            print(f"✅ 成功: {mermaid_file.name} -> {output_file.name}")
            # 修正版を元のファイルに上書き
            with open(mermaid_file, 'w', encoding='utf-8') as f:
                f.write(f"```mermaid\n{content}\n```")
            fixed_file.unlink()
            return True
        else:
            print(f"❌ 失敗: {mermaid_file.name}")
            if result.stderr:
                print(f"   エラー: {result.stderr[:300]}")
            # デバッグ用に修正ファイルを残す
            print(f"   修正版を確認: {fixed_file}")
            return False
    except Exception as e:
        print(f"❌ エラー: {mermaid_file.name} - {e}")
        return False

print("=" * 80)
print("失敗したMermaidファイルを修正して再変換します")
print("=" * 80)

success_count = 0
for filename in failed_files:
    mermaid_file = mermaid_dir / filename
    if mermaid_file.exists():
        if fix_and_convert(mermaid_file):
            success_count += 1
    else:
        print(f"⚠️  ファイルが見つかりません: {filename}")

print(f"\n✨ {success_count}/{len(failed_files)} 件の変換に成功しました")
