#!/bin/sh
# Build-time check of a cross-app origin baked into a frontend bundle.
#   check-origin <NAME> <value> required|optional
# The value must be a bare origin: http(s)://host[:port] - no path, no trailing slash.
# "required": an empty value fails the build. "optional": an empty value is allowed (the feature
# that needs it stays disabled) and a note is printed.
set -eu
name=$1
value=$2
mode=$3

if [ -z "$value" ]; then
    if [ "$mode" = "required" ]; then
        echo "ERROR: build arg $name is required (e.g. https://app.example.com)." >&2
        exit 1
    fi
    echo "NOTE: $name is empty - the cross-app hand-off that needs it is disabled in this image."
    exit 0
fi

case "$value" in
    http://?*|https://?*) ;;
    *) echo "ERROR: $name must start with https:// (or http:// for local testing): got an invalid origin." >&2; exit 1 ;;
esac
case "${value#*://}" in
    */*|*\?*|*#*) echo "ERROR: $name must be a bare origin (scheme://host[:port]) - no path, query or trailing slash." >&2; exit 1 ;;
esac
echo "$name OK"
