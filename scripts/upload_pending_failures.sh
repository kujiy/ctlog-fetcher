#!/bin/bash

API_URL="http://127.0.0.1:1173/api/worker/upload"
DIR="pending/upload_failure"

if [ ! -d "$DIR" ]; then
  echo "Directory $DIR does not exist."
  exit 1
fi

for file in "$DIR"/*.json; do
  [ -e "$file" ] || continue
  echo "Uploading $file ..."
  http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    --data-binary @"$file")
  if [ "$http_code" = "200" ]; then
    echo "Success: $file"
    mv "$file" /tmp/
  else
    echo "Failed ($http_code): $file"
  fi
done
