#!/bin/bash
# One-shot: copy a Haven-Duskholm checkout into a scratch dir, build it, boot a throwaway
# instance on a local port. Run inside WSL/Linux. Never touches SRC and never uses real data.
# Usage: setup.sh SRC_CHECKOUT [DEST=~/haven-test] [PORT=3500]
# Needs: g++-11 (or edit the Makefile CC), ccache, libcurl4-openssl-dev, libcrypt-dev.
set -eu
SRC="${1:?usage: setup.sh SRC_CHECKOUT [DEST] [PORT]}"
DEST="${2:-$HOME/haven-test}"
PORT="${3:-3500}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DEST"
( cd "$SRC" && tar --exclude=.git --exclude='*.o' --exclude='*.d' --exclude=src/haven -cf - . ) | tar -xf - -C "$DEST"
mkdir -p "$DEST/log"
( cd "$DEST/src" && make -j"$(nproc)" )
exec bash "$HERE/bootstrap.sh" "$DEST" "$PORT"
