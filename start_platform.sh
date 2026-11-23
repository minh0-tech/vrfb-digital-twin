#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export MPLCONFIGDIR="$PWD/.mplcache"
python app.py
