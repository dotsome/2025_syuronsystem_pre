#!/bin/bash
# Structured Outputs版ベンチマーク進捗モニタリング

echo "======================================================================"
echo "Structured Outputs版ベンチマーク進捗"
echo "======================================================================"
echo ""

# 総テスト数
TOTAL_TESTS=16

# 完了数をカウント
COMPLETED=$(grep -c "✅ 完了:" model_comparison_structured_live.log 2>/dev/null || echo "0")

echo "進捗: $COMPLETED / $TOTAL_TESTS テスト完了"
echo ""

# 最新の10行を表示
echo "最新ログ:"
echo "----------------------------------------------------------------------"
tail -15 model_comparison_structured_live.log 2>/dev/null || echo "ログファイルが見つかりません"
echo ""

# 平均処理時間を計算
if [ -f model_comparison_structured_live.log ]; then
    AVG_TIME=$(grep "✅ 完了:" model_comparison_structured_live.log | \
               awk '{sum+=$3} END {if(NR>0) printf "%.2f", sum/NR; else print "0"}')
    echo "平均処理時間: ${AVG_TIME}秒/テスト"

    if [ "$COMPLETED" -gt 0 ] && [ "$COMPLETED" -lt "$TOTAL_TESTS" ]; then
        REMAINING=$((TOTAL_TESTS - COMPLETED))
        EST_TIME=$(echo "$AVG_TIME * $REMAINING" | bc)
        echo "推定残り時間: ${EST_TIME}秒 (約$(echo "$EST_TIME / 60" | bc)分)"
    fi
fi

echo ""
echo "======================================================================"
