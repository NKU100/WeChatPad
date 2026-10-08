#!/usr/bin/env bash
set -euo pipefail
: "${WECHATPAD_ADB_SOCKET:?Disposable emulator socket is required}"
: "${WECHATPAD_ADB_SERIAL:?Disposable emulator serial is required}"
case "${1:-}" in
  shell|exec-out|push|pull|install|uninstall|logcat|reboot|root|unroot|wait-for-device|get-state|version|help) ;;
  *) echo 'Use a device command; the emulator and ADB server are fixed by the controller.' >&2; exit 2 ;;
esac
exec env ADB_SERVER_SOCKET="localfilesystem:$WECHATPAD_ADB_SOCKET" \
  "${ANDROID_HOME:?Android SDK is required}/platform-tools/adb" -s "$WECHATPAD_ADB_SERIAL" "$@"
