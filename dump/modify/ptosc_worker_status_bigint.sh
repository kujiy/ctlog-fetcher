#!/bin/bash
# WorkerStatusテーブルのstart, end, current, last_uploaded_indexをBIGINTにオンラインで変更

pt-online-schema-change \
--alter "MODIFY COLUMN start BIGINT, MODIFY COLUMN end BIGINT, MODIFY COLUMN current BIGINT, MODIFY COLUMN last_uploaded_index BIGINT" \
--chunk-index=PRIMARY \
--chunk-time=0.5 \
--nocheck-unique-key-change \
--skip-check-replica-lag \
--skip-check-slave-lag \
--recursion-method=none \
--set-vars "lock_wait_timeout=5,innodb_lock_wait_timeout=5" \
--dry-run \
"h=192.168.0.180,D=ct,t=worker_status,u=root,p="

pt-online-schema-change \
--alter "MODIFY COLUMN start BIGINT, MODIFY COLUMN end BIGINT, MODIFY COLUMN current BIGINT, MODIFY COLUMN last_uploaded_index BIGINT" \
--chunk-index=PRIMARY \
--chunk-time=0.5 \
--nocheck-unique-key-change \
--skip-check-replica-lag \
--skip-check-slave-lag \
--recursion-method=none \
--set-vars "lock_wait_timeout=5,innodb_lock_wait_timeout=5" \
--execute \
"h=192.168.0.180,D=ct,t=worker_status,u=root,p="

