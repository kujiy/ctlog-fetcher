#!/bin/bash
# Certテーブルのct_indexをBIGINTにオンラインで変更

PT="pt-online-schema-change"
HOST="192.168.0.180"
USER="root"
DB="ct"
TABLE="certs"

$PT --alter "MODIFY COLUMN ct_index BIGINT" \
  --chunk-index=PRIMARY \
  --chunk-time=0.5 \
  --nocheck-unique-key-change \
  --skip-check-replica-lag \
  --skip-check-slave-lag \
  --recursion-method=none \
  --set-vars "lock_wait_timeout=5,innodb_lock_wait_timeout=5" \
  --execute \
  "h=$HOST,D=$DB,t=$TABLE,u=$USER,p="
