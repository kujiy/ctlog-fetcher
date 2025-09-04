#!/bin/bash
# WorkerStatusテーブルのstart, end, current, last_uploaded_indexをBIGINTにオンラインで変更
# レプリカ遅延監視を無効化 (--check-slave-lag=no) でエラー回避

PT="pt-online-schema-change"
HOST="192.168.0.180"
USER="root"
DB="ct"
TABLE="worker_status"

$PT --alter "MODIFY COLUMN start BIGINT, MODIFY COLUMN end BIGINT, MODIFY COLUMN current BIGINT, MODIFY COLUMN last_uploaded_index BIGINT" \
  --chunk-index=PRIMARY \
  --chunk-time=0.5 \
  --nocheck-unique-key-change \
  --set-vars "lock_wait_timeout=5,innodb_lock_wait_timeout=5" \
  --no-check-slave-lag \
  --recursion-method=none 
  --execute \
  "h=$HOST,D=$DB,t=$TABLE,u=$USER"
