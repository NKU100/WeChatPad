# 兼容检测 CI

工作流 `Check WeChat compatibility` 只由 GitHub Actions 手动触发，不设每日计划。每次运行会检查清单里的所有已登记构建，并从微信官网首页发现当前最高版本的 ARM64 APK 候选。

## 检查流程

1. 已登记版本只允许使用清单中的 HTTPS 腾讯 CDN 地址 `dldir1v6.qq.com/weixin/android/`，并以预期 APK SHA-256 为缓存键。
2. 最新候选从 `https://weixin.qq.com/` 首页发现。脚本只接受官网列出的腾讯 CDN ARM64 直链，并选择唯一的最高版本；没有候选、多个并列候选或页面结构变化都会失败，不切换到第三方来源。
3. 工作流先运行候选发现、缓存校验和共用兼容核心的单元测试，再开始下载和检查。
4. 最新候选以直链 URL 的 SHA-256 定位缓存，APK 文件本身按实际 SHA-256 命名。缓存命中时会核对官网的 `Last-Modified`、`Content-Length`，重新计算 APK 摘要，并在该地址已登记时与清单摘要比较；信息缺失或变化时重新下载。
5. 调用 `compat-checker`，由模块和桌面检查器共用的 `compat-core` 校验包名、版本、ABI、签名、APK 摘要和已登记 Hook 特征。
6. 已登记构建和最新候选分别上传诊断报告。检查失败时仍保留报告 artifact 和 Actions 日志。

在仓库的 **Actions** 页面选择 **Check WeChat compatibility**，再点 **Run workflow** 即可运行。工作流只读取仓库内容，不使用签名 Secrets，也不创建或修改 PR。

## 处理新版本

工作流会自动下载当前官网候选。如果版本已在 `compatibility/targets.json` 登记，就执行完整 profile 检查；如果尚未登记，检查器报告 `UNKNOWN_BUILD` 并上传该 APK 的包名、版本、ABI、签名和 SHA-256 诊断，不猜测 Hook 目标。

要支持新版本，仍需先人工分析 Hook 特征，再将完整构建身份和规则加入清单。下一次手动运行会同时回归新版本与旧版本。静态检查通过后，还要在本地 AVD 完成运行时冒烟；当前工作流不改清单、不创建 PR，也不设每日计划。
