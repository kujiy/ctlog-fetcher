#!/bin/sh

## --- Set mydns.jp information ---
#MASTER_ID="YOUR_MASTER_ID"
#PASSWORD="YOUR_PASSWORD"
## -----------------------------

. .env

# mydns.jpにIPアドレスを通知
curl -u ${MASTER_ID}:${PASSWORD} "http://www.mydns.jp/login.html"
