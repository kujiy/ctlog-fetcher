#!/bin/bash
# Certテーブルのct_indexをBIGINTにオンラインで変更

PT="pt-online-schema-change"
HOST="192.168.0.180"
USER="root"
DB="ct"
TABLE="certs"

$PT --alter "MODIFY COLUMN ct_index BIGINT NULL DEFAULT NULL" \
  --chunk-index=PRIMARY \
  --check-interval=1 \
  --chunk-time=0.5 \
  --chunk-size=200 \
  --max-load="Threads_running=80" \
  --critical-load="Threads_running=240" \
  --skip-check-replica-lag \
  --skip-check-slave-lag \
  --recursion-method=none \
  --set-vars "lock_wait_timeout=120,innodb_lock_wait_timeout=120" \
  --progress time,30 \
  --execute \
  "h=$HOST,D=$DB,t=$TABLE,u=$USER,p="
