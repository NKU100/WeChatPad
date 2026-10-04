# WeChatPad 本地运行时冒烟记录

日期：2026-10-05

## 环境

- AVD：专用本地 Android 37.2 ARM64 虚拟设备，测试时保持窗口可见。
- 系统：Android 17，API 37，ARM64，16 KB page size。
- 系统镜像：基于 Google Play ARM64 16 KB 镜像的独立副本；副本的 ramdisk 已修改，保留的原始 ramdisk 与基准镜像一致。
- Root：Magisk 31.0。`su -c id` 返回 `uid=0(root)` 和 `context=u:r:magisk:s0`。
- 框架：官方 LSPosed `v2.2.0 (7854)`，`lspd` 进程运行；WeChatPad 在 LSPosed 中以 API 102 加载。
- 模块：`io.github.nku100.wechatpad` 0.1.0，只作用于 `com.tencent.mm`。
- 测试期间，参考模块 WeChatTablet 1.0.4 保持安装，但关闭其微信作用域；基线时 WeChatPad 关闭，Hook 验收时 WeChatPad 开启。
- AVD 上未登录微信账号。二维码只用于确认页面可达，没有扫描或登录。

本地复现时使用独立的 Android 17 / API 37.2、ARM64、16 KB pages Google Play 系统镜像 AVD。可使用 [NKU100/rootAVD@a0defa2](https://github.com/NKU100/rootAVD/tree/a0defa2) 为 ramdisk 配置 Magisk 31.0；补丁后冷启动，在 Magisk Superuser 中允许 `com.android.shell`，并用 `adb shell su -c 'id && magisk -v && magisk -V'` 验证 root。该组合也记录在 Zygisk 模板仓库的 root AVD 验证说明中。随后安装支持 API 102 的官方 LSPosed。

当前设备的 `su` 输出确认 root 由 Magisk 提供。镜像副本、原始 ramdisk 备份和模板记录均与 rootAVD 流程相符，但没有保留这台 AVD 当时的执行日志，因此不能确认历史操作的具体命令或 revision。AVD 名称、ADB serial 和主机配置路径由本机自行管理，不纳入仓库。

## 结果

| 微信版本 | 无模块基线 | WeChatPad 运行时 | 登录页面冒烟 |
| --- | --- | --- | --- |
| 8.0.69 (3040) | 首次登录流程进入手机号登录页；没有平板登录入口 | `COMPATIBLE`，两处目标唯一解析，安装 2 个 Hook；缓存未命中 | 平板入口出现；进入 `MobileInputUI` 后可选“Logged in on Phone & Tablet”，打开 `LoginAsExDeviceUI` 二维码页 |
| 8.0.79 (3200) | 首次登录流程进入手机号登录页；没有平板登录入口 | `COMPATIBLE`，两处目标唯一解析，安装 2 个 Hook；缓存未命中 | 平板入口出现；进入 `MobileInputUI` 后可选“Logged in on Phone & Tablet”，打开 `LoginAsExDeviceUI` 二维码页 |

具体运行时解析结果：

- 8.0.69：APK SHA-256 `e4da5809f2b3305e375db38897a4082085adc6b51182fa807813c4dda1c3a948`；平板方法 `Lcom/tencent/mm/ui/qj;->B(Lfd5/n0;)Z`，登录入口方法 `Lg21/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V`。
- 8.0.79：APK SHA-256 `5feb100337981467fd257c3ad66bb171f54a69d2579b2ecc70d5a628db8e7282`；平板方法 `Lcom/tencent/mm/ui/ok;->C(Lpv5/w0;)Z`，登录入口方法 `Lfb1/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V`。
- 两版运行时日志均显示微信主进程兼容、Hook 安装成功，并明确跳过 `com.tencent.mm:push` 辅助进程。
- 先在 8.0.69 运行，再升级回 8.0.79：8.0.79 首次启动因 APK 安装指纹变化记录 `cacheHit=false` 并重新解析；随后冷启动记录 `cacheHit=true`，两个 Hook 仍成功安装。

首次查看 8.0.79 时，WeChatTablet 的微信作用域仍开启，因此那次页面不作为无模块基线。关闭该作用域并重启微信后，重新采集了基线；所有正式结果均在参考模块不作用于微信时取得。

## 结论

两版均完成无模块基线、WeChatPad 注入、平板登录入口可见和二维码页可达的本地冒烟。`compatibility/targets.json` 中两个目标标为 `runtime-verified-local`。本结果只证明客户端登录界面路径可用，不代表微信服务器接受同一账号的多台移动设备会话。
