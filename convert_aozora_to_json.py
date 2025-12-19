#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""青空文庫テキストをJSON形式に変換（ルビ削除、章分け）"""

import json
import re
import sys

def remove_ruby(text):
    """ルビを削除（《》で囲まれた部分）"""
    # ｜から始まるルビ（例: 中央｜亜細亜《アジア》）
    text = re.sub(r'｜[^《]*《[^》]*》', '', text)
    # 通常のルビ（例: 黄巾賊《こうきんぞく》）
    text = re.sub(r'《[^》]*》', '', text)
    return text

def remove_annotations(text):
    """入力者注を削除（［＃...］形式）"""
    # ただし章見出しマーカーは残す
    text = re.sub(r'［＃[^］]*］', '', text)
    return text

def extract_chapters(text):
    """章を抽出"""
    chapters = []

    # 見出しパターン（大見出しと中見出し）
    # ［＃○字下げ］タイトル［＃「タイトル」は大見出し/中見出し］
    heading_pattern = r'［＃\d+字下げ］([^［\n]+)［＃「[^」]+」は(?:大見出し|中見出し)］'

    # 見出しを検索
    headings = list(re.finditer(heading_pattern, text))

    if not headings:
        # 見出しがない場合は全体を1章として扱う
        clean_text = remove_ruby(text)
        clean_text = remove_annotations(clean_text)
        clean_text = clean_text.strip()
        if clean_text:
            chapters.append({
                'section': '1',
                'title': '本文',
                'text': clean_text
            })
        return chapters

    # 本文開始位置を探す（最初の見出しまで）
    first_heading_pos = headings[0].start()

    # 各見出し間のテキストを抽出
    for i, heading in enumerate(headings):
        title = heading.group(1).strip()

        # 次の見出しまたは終端までのテキストを取得
        start_pos = heading.end()
        if i + 1 < len(headings):
            end_pos = headings[i + 1].start()
        else:
            end_pos = len(text)

        chapter_text = text[start_pos:end_pos]

        # ルビと注釈を削除
        chapter_text = remove_ruby(chapter_text)
        chapter_text = remove_annotations(chapter_text)
        chapter_text = chapter_text.strip()

        if chapter_text:
            chapters.append({
                'section': str(i + 1),
                'title': title,
                'text': chapter_text
            })

    return chapters

def convert_file(input_file, output_file):
    """青空文庫テキストをJSON形式に変換"""
    # ファイル読み込み（cp932エンコーディング）
    with open(input_file, 'r', encoding='cp932') as f:
        text = f.read()

    # ヘッダー部分（-------で囲まれた部分）を削除
    text = re.sub(r'-{50,}.*?-{50,}', '', text, flags=re.DOTALL)

    # 章を抽出
    chapters = extract_chapters(text)

    # JSON形式で保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)

    print(f"変換完了: {input_file} → {output_file}")
    print(f"章数: {len(chapters)}")

def main():
    if len(sys.argv) != 3:
        print("使用法: python convert_aozora_to_json.py <入力ファイル> <出力ファイル>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    convert_file(input_file, output_file)

if __name__ == '__main__':
    # コマンドライン引数がない場合はデフォルト変換
    if len(sys.argv) == 1:
        # sangokuとranpoを変換
        convert_file('sangoku.txt', 'sangoku_text.json')
        convert_file('ranpo.txt', 'ranpo_text.json')
    else:
        main()
