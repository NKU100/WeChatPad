# 兼容检测 CI

工作流 `Check WeChat compatibility` 只由 GitHub Actions 手动触发，不设每日计划。它检查 `compatibility/targets.json` 中登记的所有构建，因此新增候选版本后也会回归全部已登记版本。

## 检查流程

1. 读取每个 profile 的官方 APK 地址和预期 SHA-256。当前只允许 HTTPS 腾讯 CDN 地址 `dldir1v6.qq.com/weixin/android/`。
2. 按 APK SHA-256 恢复缓存；缓存不存在或摘要不符时重新下载，并在使用前校验 SHA-256。
3. 调用 `compat-checker`，由模块和桌面检查器共用的 `compat-core` 校验包名、版本、ABI、签名、APK 摘要和 Hook 特征。
4. 每个版本单独上传一份诊断报告。检查失败时仍保留报告 artifact 和 Actions 日志。

在仓库的 **Actions** 页面选择 **Check WeChat compatibility**，再点 **Run workflow** 即可运行。工作流只读取仓库内容，不使用签名 Secrets，也不创建或修改 PR。

## 增加候选版本

先从腾讯官方来源取得 APK，并在本地完成候选特征分析；然后在 `compatibility/targets.json` 中新增完整的构建身份、官方下载地址、APK SHA-256、签名摘要和 Hook 规则。手动运行工作流后，它会同时检查新候选和清单里的旧版本。CI 静态检查通过后，仍需在本地 AVD 完成运行时冒烟，才能把它记录为正式运行时兼容版本。

当前工作流不抓取官网来自动发现最新版本，也不推测或生成 Hook 规则；这些自动发现和 PR 生成留待后续阶段。
