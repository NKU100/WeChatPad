# AVD root ramdisk 制作

[`environment/avd-runtime.json`](../../environment/avd-runtime.json) 固定 Google 系统镜像、Magisk、原始 ramdisk 和补丁产物的版本与摘要。制作脚本使用官方 Magisk APK 中的 `magiskboot`，不需要付费服务或 Codex。

目标为 API 37.2、`google_apis_ps16k`、x86_64、r06，Magisk 31.0。脚本只生成 ramdisk，不安装 LSPosed，也不修改已有 AVD 的镜像或启动配置。

## Linux 本机制作

需要 Python 3.9 或以上及 curl。支持 x86_64、ARM64 Linux；修补工具架构按主机选择，嵌入 ramdisk 的 payload 始终由清单指定为 x86_64。

在仓库根目录执行：

```sh
python3 scripts/environment/build_ramdisk.py \
  --output work/ramdisk-build/result
```

首次会下载约 2.4 GB 的官方系统镜像 ZIP 和 Magisk APK。缓存按输入摘要命名，复用前重新校验。已有完整系统 ZIP 时，可以传入 `--system-image-zip`；脚本仍检查 Google 清单记录的 SHA-1，并检查提取后的 ramdisk SHA-256。

如果 Android SDK 已安装固定镜像，可避免重新下载整个 ZIP：

```sh
python3 scripts/environment/build_ramdisk.py \
  --stock-ramdisk "$ANDROID_HOME/system-images/android-37.2/google_apis_ps16k/x86_64/ramdisk.img" \
  --output work/ramdisk-build/result
```

该路径只读取并校验原始文件，不覆盖 SDK 镜像。必须使用未修补的原始 ramdisk；摘要不匹配时停止。`--magisk-apk` 可复用已有官方 APK，同样必须通过固定 SHA-256 校验。

## macOS 通过独立 AVD 制作

macOS 无法直接运行 APK 内的 Linux ELF 工具。启动专用于制作的 ARM64 或 x86_64 Android AVD，通过 `adb devices` 确认设备，显式传入其 serial：

```sh
python3 scripts/environment/build_ramdisk.py \
  --serial "$BUILDER_SERIAL" \
  --stock-ramdisk "$ANDROID_HOME/system-images/android-37.2/google_apis_ps16k/x86_64/ramdisk.img" \
  --output work/ramdisk-build/result
```

`BUILDER_SERIAL` 由本机选择，不存入仓库。制作 AVD 只负责执行 `magiskboot`，不需要 root、Magisk 或 LSPosed，也不必与目标系统版本相同。脚本拒绝实体设备 serial；在所选 AVD 的 `/data/local/tmp` 创建独立临时目录，结束时清理该目录。输入和输出通过 ADB 传输，目标 payload 架构不随制作 AVD 改变。

## 修补步骤

1. 校验原始 ramdisk 和官方 Magisk APK。
2. 用 `magiskboot` 解压原始 ramdisk。
3. 合并两个 newc CPIO archive；重名条目以后一个 archive 为准，保留原始条目和顺序。
4. 从 APK 提取工具及 x86_64 的 `magiskinit`、`magisk`、`init-ld` 和 stub APK。
5. 将 `init` 替换为 `magiskinit`，加入压缩 payload，并用 Magisk 备份原始 init。
6. 保留 `KEEPVERITY=true`、`KEEPFORCEENCRYPT=true`、`RECOVERYMODE=false`，按原有 `lz4_legacy` 格式压缩。
7. 要求最终 ramdisk SHA-256 与清单中的已验证产物一致；不一致即失败。

修补操作对应 [Magisk 31.0 的官方 boot patch 实现](https://github.com/topjohnwu/Magisk/blob/v31.0/scripts/boot_patch.sh)。此配方保留当前已验证 AVD 的配置，不用于手机刷机。

## 输出与验收

输出目录必须为空，成功后包含：

- `ramdisk37-patched.img`：与当前 Release 产物逐字节一致的 ramdisk。
- `manifest.json`：输入版本与摘要、工具架构与摘要、配方摘要及复现结果；不包含主机路径或设备 serial。

仅传入原始 ramdisk 时，manifest 的 `systemArchiveVerified` 为 false，表示未校验完整 ZIP；原始 ramdisk SHA-256 仍已校验。所有产物和下载缓存保留在 Git 忽略的工作目录中。脚本不会自动上传或覆盖 Release。

在 GitHub Actions 手动运行 **Validate registered WeChat runtime**，勾选 `rebuild_ramdisk`，即可从 SDK 原始 ramdisk 和已验证 Magisk APK 重建，校验预期哈希，并与 Release 文件执行 `cmp`。随后继续完整 AVD 冒烟，确认启动、Magisk root、LSPosed 注入、登录入口及稳定二维码页；结果 artifact 包含 `ramdisk-reproduction.json`。

字节复现与启动验证是两项独立证据。升级镜像或 Magisk 时，更新清单并重新审查配方、生成候选产物和运行时验收；不能把新摘要直接当作已经验证的基线。
