#!/bin/bash
# モデル比較実験をバックグラウンドで実行するスクリプト

echo "モデル比較実験を開始します..."
echo "実行ログ: model_test_output.log"
echo ""

# タイムスタンプ
echo "開始時刻: $(date)" > model_test_output.log

# バックグラウンドで実行
nohup python model_comparison_test.py >> model_test_output.log 2>&1 &

# プロセスIDを保存
echo $! > model_test.pid

echo "✅ バックグラウンドで実行を開始しました"
echo "プロセスID: $(cat model_test.pid)"
echo ""
echo "進捗確認方法:"
echo "  tail -f model_test_output.log"
echo ""
echo "停止方法:"
echo "  kill \$(cat model_test.pid)"
echo ""
