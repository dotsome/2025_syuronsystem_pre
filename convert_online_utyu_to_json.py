#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
online_utyu.txt を online_utyu_text.json に変換
"""

import json
import re

def parse_online_utyu(filepath):
    """
    online_utyu.txt を読み込んで JSON 形式に変換
    章形式: ペスカトーレ①, ブリュンヒルデ①, 雌伏① など（カタカナ/漢字+丸数字）
    """
    # UTF-8 エンコーディングで読み込み
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    chapters = []

    lines = content.split('\n')

    current_section = None
    current_title = None
    current_text = []

    # 章タイトルのパターン: カタカナ/ひらがな/漢字 + 丸数字
    chapter_pattern = re.compile(r'^([ぁ-ゟァ-ヺ一-龯ー・]+)([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿])$')

    # 丸数字から通常の数字への変換辞書
    circle_to_num = {
        '①': 1, '②': 2, '③': 3, '④': 4, '⑤': 5, '⑥': 6, '⑦': 7, '⑧': 8, '⑨': 9, '⑩': 10,
        '⑪': 11, '⑫': 12, '⑬': 13, '⑭': 14, '⑮': 15, '⑯': 16, '⑰': 17, '⑱': 18, '⑲': 19, '⑳': 20,
        '㉑': 21, '㉒': 22, '㉓': 23, '㉔': 24, '㉕': 25, '㉖': 26, '㉗': 27, '㉘': 28, '㉙': 29, '㉚': 30,
        '㉛': 31, '㉜': 32, '㉝': 33, '㉞': 34, '㉟': 35, '㊱': 36, '㊲': 37, '㊳': 38, '㊴': 39, '㊵': 40,
        '㊶': 41, '㊷': 42, '㊸': 43, '㊹': 44, '㊺': 45, '㊻': 46, '㊼': 47, '㊽': 48, '㊾': 49, '㊿': 50
    }

    section_counter = 1

    for line in lines:
        # 章タイトルの検出
        chapter_match = chapter_pattern.match(line.strip())
        if chapter_match:
            # 前のセクションを保存
            if current_section is not None and current_text:
                chapters.append({
                    "section": str(current_section),
                    "title": current_title if current_title else "",
                    "text": '\n'.join(current_text).strip()
                })

            # 新しいセクション開始
            current_section = section_counter
            current_title = line.strip()  # タイトル全体を保存（丸数字含む）
            current_text = []
            section_counter += 1
        else:
            # 本文として追加
            if current_section is not None:
                current_text.append(line)

    # 最後のセクションを保存
    if current_section is not None and current_text:
        chapters.append({
            "section": str(current_section),
            "title": current_title if current_title else "",
            "text": '\n'.join(current_text).strip()
        })

    return chapters

def main():
    input_file = '/Users/saitoudaisuke/Documents/GitHub/2025_syuronsystem_pre/online_utyu.txt'
    output_file = '/Users/saitoudaisuke/Documents/GitHub/2025_syuronsystem_pre/online_utyu_text.json'

    print(f"Reading {input_file}...")
    chapters = parse_online_utyu(input_file)

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
