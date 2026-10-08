#!/usr/bin/env bash
set -euo pipefail

sdk_relative=$(python3 -c 'import json; print(json.load(open("environment/avd-runtime.json"))["systemImage"]["package"].replace(";", "/"))')
stock_ramdisk="${ANDROID_HOME:?Android SDK is required}/$sdk_relative/ramdisk.img"
expected_sha256=$(python3 -c 'import json; print(json.load(open("environment/avd-runtime.json"))["systemImage"]["stockRamdiskSha256"])')
printf '%s  %s\n' "$expected_sha256" "$stock_ramdisk" | sha256sum --check

selected_ramdisk=work/runtime-smoke/ramdisk37-patched.img
if [[ "${REBUILD_RAMDISK:-false}" == 'true' ]]; then
  python3 scripts/environment/build_ramdisk.py \
    --stock-ramdisk "$stock_ramdisk" \
    --magisk-apk work/runtime-smoke/magisk.apk \
    --output work/ramdisk-build/result
  cmp work/ramdisk-build/result/ramdisk37-patched.img "$selected_ramdisk"
  cp work/ramdisk-build/result/manifest.json work/runtime-smoke/evidence/ramdisk-reproduction.json
  selected_ramdisk=work/ramdisk-build/result/ramdisk37-patched.img
fi
cp "$selected_ramdisk" "$stock_ramdisk"
