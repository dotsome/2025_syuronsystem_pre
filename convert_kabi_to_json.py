#!/usr/bin/env python3
"""
kabi.txtを章ごとに分割してJSON形式に変換するスクリプト
章番号は漢数字で表されている（一、二、三...七十九）
"""

import json
import re
from pathlib import Path

def convert_kabi_to_json(input_file: str, output_file: str):
    """
    kabi.txtを読み込んで章ごとに分割し、JSON形式で出力

    Args:
        input_file: 入力テキストファイルのパス
        output_file: 出力JSONファイルのパス
    """

    # テキストを読み込み
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 章の区切りパターン（漢数字の章番号）
    chapter_pattern = re.compile(r'^　　　　　([一二三四五六七八九十百千]+)\s*$')

    chapters = {}
    current_chapter = None
    current_content = []

    for line in lines:
        match = chapter_pattern.match(line)

        if match:
            # 前の章を保存
            if current_chapter is not None:
                chapters[current_chapter] = ''.join(current_content).strip()

            # 新しい章を開始
            current_chapter = match.group(1)
            current_content = []

        elif current_chapter is not None:
            # 章の内容を追加
            # 空行は除外せず、そのまま保持
            if line.strip():  # 空行でなければ追加
                current_content.append(line)

        elif not match and current_chapter is None:
            # 第一章より前の内容（序章扱い）
            if '序章' not in chapters:
                chapters['序章'] = []
            if line.strip():
                chapters['序章'].append(line)

    # 最後の章を保存
    if current_chapter is not None:
        chapters[current_chapter] = ''.join(current_content).strip()

    # 序章があれば文字列に変換
    if '序章' in chapters:
        chapters['序章'] = ''.join(chapters['序章']).strip()

    # JSONとして保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)

    print(f"変換完了: {len(chapters)}章")
    print(f"出力ファイル: {output_file}")

    # 統計情報を表示
    total_chars = sum(len(content) for content in chapters.values())
    print(f"総文字数: {total_chars:,}")
    print(f"平均文字数/章: {total_chars // len(chapters):,}")

if __name__ == "__main__":
    input_file = "kabi.txt"
    output_file = "kabi.json"

    convert_kabi_to_json(input_file, output_file)
