#!/bin/sh

set -eu
cd "$(dirname "$0")"

[ -f .env ] || cp .env.example .env

fill() {
  if grep -q "^$1=\$" .env; then
    VALUE="$2" perl -pi -e 's!^'"$1"'=$!'"$1"'=$ENV{VALUE}!' .env
    echo "diisi: $1"
  fi
}

fill SESSION_SECRET "$(openssl rand -hex 32)"
fill MASTER_KEY "$(openssl rand -base64 32)"
fill BLIND_INDEX_KEY "$(openssl rand -hex 32)"