#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
saogoku_2.txt を sangoku_2_text.json に変換
ルビを保持したまま JSON 形式にする
"""

import json
import re

def parse_sangoku_2_with_ruby(filepath):
    """
    saogoku_2.txt を読み込んでルビ付きで JSON 形式に変換
    青空文庫形式: 漢字《かんじ》
    """
    # Shift-JIS エンコーディングで読み込み
    with open(filepath, 'r', encoding='shift_jis', errors='ignore') as f:
        content = f.read()

    chapters = []

    # セクション分割のパターン（青空文庫形式）
    # ヘッダー部分をスキップ
    lines = content.split('\n')

    current_section = None
    current_title = None
    current_text = []

    in_header = True
    section_counter = 1  # 最初のセクション番号

    for line in lines:
        line = line.strip()

        # ヘッダー終了の検出
        if in_header:
            if '-------------------------------------------------------' in line:
                in_header = False
            continue

        # 空行はスキップ
        if not line:
            continue

        # 章タイトルの検出（青空文庫形式）
        # ［＃７字下げ］一［＃「一」は中見出し］のような形式
        chapter_match = re.match(r'［＃.*字下げ］([一二三四五六七八九十百千]+|[0-9]+)［＃.*中見出し.*］', line)
        if chapter_match:
            # 前のセクションを保存
            if current_section is not None and current_text:
                chapters.append({
                    "section": str(current_section),
                    "title": current_title if current_title else "",
                    "text": '\n'.join(current_text)
                })

            # 新しいセクション開始
            current_section = section_counter
            current_title = chapter_match.group(1)
            current_text = []
            section_counter += 1
        # 大見出しはスキップ（黄巾賊など）
        elif '［＃' in line and '大見出し' in line:
            continue
        # 注釈をスキップ
        elif line.startswith('［＃') and line.endswith('］'):
            continue
        else:
            # 本文として追加（ルビはそのまま保持）
            if current_section is not None:
                current_text.append(line)

    # 最後のセクションを保存
    if current_section is not None and current_text:
        chapters.append({
            "section": str(current_section),
            "title": current_title if current_title else "",
            "text": '\n'.join(current_text)
        })

    return chapters

def main():
    input_file = '/Users/saitoudaisuke/Documents/GitHub/2025_syuronsystem_pre/saogoku_2.txt'
    output_file = '/Users/saitoudaisuke/Documents/GitHub/2025_syuronsystem_pre/sangoku_2_text.json'

    print(f"Reading {input_file}...")
    chapters = parse_sangoku_2_with_ruby(input_file)

    print(f"Found {len(chapters)} chapters")

    # JSON に保存（ensure_ascii=False でルビ付き日本語をそのまま保存）
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
