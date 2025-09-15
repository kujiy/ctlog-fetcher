#!/bin/bash

url="https://ct.googleapis.com/logs/eu1/xenon2024/ct/v1/get-entries?start=0&end=0"
count=0

while true; do
    # ヘッダを一時ファイルに保存
    headers=$(mktemp)
    body=$(mktemp)
    curl -s -D "$headers" -o "$body" "$url"
    code=$(head -n 1 "$headers" | awk '{print $2}')
    count=$((count+1))
    echo "[$count] HTTP $code"

    if [ "$code" -ne 200 ]; then
        echo "---- Non-200 Response ----"
        cat "$headers"
        rm -f "$headers" "$body"
        break
    fi

    rm -f "$headers" "$body"
done

