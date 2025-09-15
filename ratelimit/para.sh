#!/bin/bash

url="https://ct.googleapis.com/logs/eu1/xenon2024/ct/v1/get-entries?start=0&end=0"

# 1000回まで並列で試す
seq 1 1000 | xargs -n1 -P20 -I{} bash -c '
  headers=$(mktemp)
  curl -s -D "$headers" -o /dev/null "'"$url"'"
  code=$(head -n 1 "$headers" | awk "{print \$2}")
  if [ "$code" -ne 200 ]; then
    echo "---- Non-200 Response ----"
    cat "$headers"
    rm -f "$headers"
    # プロセスを止める
    kill -TERM $PPID
    exit 1
  fi
  rm -f "$headers"
'

