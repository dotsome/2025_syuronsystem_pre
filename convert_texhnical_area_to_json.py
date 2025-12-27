#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
texhnical_area.txt を texhnical_area_text.json に変換
"""

import json
import re

def parse_texhnical_area(filepath):
    """
    texhnical_area.txt を読み込んで JSON 形式に変換
    章形式: 1.入学前, 2.３月２７日　８：１５ など
    """
    # UTF-8 エンコーディングで読み込み
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    chapters = []

    lines = content.split('\n')

    current_section = None
    current_title = None
    current_text = []

    # 章タイトルのパターン: 数字.タイトル
    chapter_pattern = re.compile(r'^(\d+)\.(.*)')

    for line in lines:
        # 章タイトルの検出
        chapter_match = chapter_pattern.match(line)
        if chapter_match:
            # 前のセクションを保存
            if current_section is not None and current_text:
                chapters.append({
                    "section": str(current_section),
                    "title": current_title.strip() if current_title else "",
                    "text": '\n'.join(current_text).strip()
                })

            # 新しいセクション開始
            current_section = int(chapter_match.group(1))
            current_title = chapter_match.group(2)
            current_text = []
        else:
            # 本文として追加
            if current_section is not None:
                current_text.append(line)

    # 最後のセクションを保存
    if current_section is not None and current_text:
        chapters.append({
            "section": str(current_section),
            "title": current_title.strip() if current_title else "",
            "text": '\n'.join(current_text).strip()
        })

    return chapters

def main():
    input_file = '/Users/saitoudaisuke/Documents/GitHub/2025_syuronsystem_pre/texhnical_area.txt'
    output_file = '/Users/saitoudaisuke/Documents/GitHub/2025_syuronsystem_pre/texhnical_area_text.json'

    print(f"Reading {input_file}...")
    chapters = parse_texhnical_area(input_file)

    print(f"Found {len(chapters)} chapters")

    # JSON に保存（ensure_ascii=False で日本語をそのまま保存）
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_file}")

    # サンプル表示
    if chapters:
        print(f"\nFirst chapter preview:")
        print(f"Section: {chapters[0]['section']}")
        print(f"Title: {chapters[0]['title']}")
        print(f"Text preview: {chapters[0]['text'][:200]}...")

if __name__ == '__main__':
    main()
