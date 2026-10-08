#!/usr/bin/env bash
set -euo pipefail

evidence=work/root-probe/evidence
mkdir -p "$evidence"
trap 'adb logcat -d -v threadtime > "$evidence/logcat.txt" 2>&1 || true; adb shell getprop > "$evidence/device-properties.txt" 2>&1 || true' EXIT
exec > >(tee "$evidence/root-check.txt") 2>&1

adb shell id
adb shell /debug_ramdisk/magisk -v
adb shell pidof magiskd

# Authorize shell in this disposable test device, then restore ordinary adbd.
adb root
adb wait-for-device
adb shell '/debug_ramdisk/magisk --sqlite "REPLACE INTO policies (uid,policy,until,logging,notification) VALUES (2000,2,0,1,0)"'
adb unroot
adb wait-for-device
adb shell id | tee "$evidence/shell-id.txt"
grep -F 'uid=2000(shell)' "$evidence/shell-id.txt"
adb shell /debug_ramdisk/magisk su -c id | tee "$evidence/su-id.txt"
grep -F 'uid=0(root)' "$evidence/su-id.txt"
grep -F 'context=u:r:magisk:s0' "$evidence/su-id.txt"
adb shell /debug_ramdisk/magisk su -c '/debug_ramdisk/magisk -v; /debug_ramdisk/magisk -V' | tee "$evidence/magisk-version.txt"
grep -Fx '31000' "$evidence/magisk-version.txt"
touch "$evidence/root-verified.txt"
