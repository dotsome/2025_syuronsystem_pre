#!/usr/bin/env python3
"""
すべてのMermaidファイルをPNG画像に変換
"""
import subprocess
from pathlib import Path

def convert_mermaid_to_png(mermaid_file: Path, output_file: Path) -> bool:
    """MermaidファイルをPNG画像に変換"""
    try:
        # Mermaidファイルを読み込み
        with open(mermaid_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # ```mermaid マーカーを削除
        if '```mermaid' in content:
            content = content.split('```mermaid', 1)[1]
            if '```' in content:
                content = content.split('```', 1)[0]

        content = content.lstrip('\n')
        content = content.replace('<br/>', '<br>')

        # 一時ファイルに保存
        temp_file = mermaid_file.with_suffix('.tmp.mmd')
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # mmdc で変換
        cmd = [
            'mmdc',
            '-i', str(temp_file),
            '-o', str(output_file),
            '-b', 'transparent',
            '-w', '800',
            '-H', '600'
        ]

        subprocess.run(cmd, check=True, capture_output=True, text=True)

        # 一時ファイルを削除
        temp_file.unlink()

        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {mermaid_file.name}: {e.stderr[:100]}")
        if temp_file.exists():
            temp_file.unlink()
        return False
    except Exception as e:
        print(f"❌ {mermaid_file.name}: {str(e)}")
        return False

if __name__ == "__main__":
    mermaid_dir = Path(__file__).parent / "mermaid_outputs"

    # すべての.mmdファイルを取得
    mmd_files = sorted(mermaid_dir.glob("*.mmd"))

    print(f"🖼️  {len(mmd_files)}個のMermaidファイルを変換します\n")

    success_count = 0
    for mmd_file in mmd_files:
        png_file = mmd_file.with_suffix('.png')

        # 既にPNGが存在する場合はスキップ
        if png_file.exists():
            print(f"⏭️  {mmd_file.name} (既に存在)")
            success_count += 1
            continue

        if convert_mermaid_to_png(mmd_file, png_file):
            print(f"✅ {mmd_file.name} → {png_file.name}")
            success_count += 1

    print(f"\n✨ 完了: {success_count}/{len(mmd_files)} ファイルを変換しました")
