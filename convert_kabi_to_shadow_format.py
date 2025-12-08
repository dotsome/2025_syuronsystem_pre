#!/usr/bin/env python3
"""
kabi.jsonをshadow_text.jsonと同じフォーマットに変換するスクリプト
"""

import json
from pathlib import Path

def convert_kabi_to_shadow_format(input_file: str, output_file: str):
    """
    kabi.jsonを読み込んでshadow_text.json形式に変換

    Args:
        input_file: 入力JSONファイルのパス (kabi.json)
        output_file: 出力JSONファイルのパス (kabi_text.json)
    """

    # kabi.jsonを読み込み
    with open(input_file, 'r', encoding='utf-8') as f:
        kabi_data = json.load(f)

    # shadow_text.json形式に変換
    shadow_format = []

    for chapter_num, chapter_text in kabi_data.items():
        # 章番号を整数に変換（序章は0とする）
        if chapter_num == "序章":
            section_num = "0"
            title = "序章"
        else:
            # 漢数字を算用数字に変換
            kanji_to_num = {
                "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
                "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
                "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
                "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
                "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
                "三十一": 31, "三十二": 32, "三十三": 33, "三十四": 34, "三十五": 35,
                "三十六": 36, "三十七": 37, "三十八": 38, "三十九": 39, "四十": 40,
                "四十一": 41, "四十二": 42, "四十三": 43, "四十四": 44, "四十五": 45,
                "四十六": 46, "四十七": 47, "四十八": 48, "四十九": 49, "五十": 50,
                "五十一": 51, "五十二": 52, "五十三": 53, "五十四": 54, "五十五": 55,
                "五十六": 56, "五十七": 57, "五十八": 58, "五十九": 59, "六十": 60,
                "六十一": 61, "六十二": 62, "六十三": 63, "六十四": 64, "六十五": 65,
                "六十六": 66, "六十七": 67, "六十八": 68, "六十九": 69, "七十": 70,
                "七十一": 71, "七十二": 72, "七十三": 73, "七十四": 74, "七十五": 75,
                "七十六": 76, "七十七": 77, "七十八": 78, "七十九": 79
            }

            section_num = str(kanji_to_num[chapter_num])
            title = f"{section_num}章"

        shadow_format.append({
            "section": section_num,
            "title": title,
            "text": chapter_text
        })

    # JSONとして保存（shadow_text.jsonと同じフォーマット）
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(shadow_format, f, ensure_ascii=False, indent=2)

    print(f"変換完了: {len(shadow_format)}章")
    print(f"出力ファイル: {output_file}")

if __name__ == "__main__":
    input_file = "kabi.json"
    output_file = "kabi_text.json"

    convert_kabi_to_shadow_format(input_file, output_file)
