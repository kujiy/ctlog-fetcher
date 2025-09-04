#!/bin/bash
# WorkerLogStatテーブルのworker_total_count, jp_count_sumをBIGINTにオンラインで変更

PT="pt-online-schema-change"
HOST="192.168.0.180"
USER="root"
DB="ct"
TABLE="worker_log_stats"

$PT --alter "MODIFY COLUMN worker_total_count BIGINT, MODIFY COLUMN jp_count_sum BIGINT" \
  --chunk-index=PRIMARY \
  --chunk-time=0.5 \
  --nocheck-unique-key-change \
  --skip-check-replica-lag \
  --skip-check-slave-lag \
  --recursion-method=none \
  --set-vars "lock_wait_timeout=5,innodb_lock_wait_timeout=5" \
  --execute \
  "h=$HOST,D=$DB,t=$TABLE,u=$USER,p="
