# 兼容检测 CI

工作流 `Check WeChat compatibility` 只由 GitHub Actions 手动触发，不设每日计划。它从微信官网首页发现最高版本的 ARM64 APK 候选，并按候选版本选择静态回归窗口。新候选加上版本码最高的两个已正式支持旧版；候选已正式支持时检查最近三个正式支持版本。报告会列明本次实际检查的版本，历史 profile 不会因此从清单移除。

## 检查流程

1. 已登记 APK 只允许使用清单中的 HTTPS 腾讯 CDN 地址 `dldir1v6.qq.com/weixin/android/`，并以预期 APK SHA-256 为缓存键。
2. 最新候选从 `https://weixin.qq.com/` 首页发现。脚本只接受官网列出的腾讯 CDN ARM64 直链，并选择唯一的最高版本；没有候选、多个并列候选或页面结构变化都会失败，不切换到第三方来源。
3. 候选版本码用于选择最多两个较早的 `runtime-verified-local` profile；候选自身另行检查，因此每轮最多覆盖三个不同版本。
4. 候选 APK 以官方直链 SHA-256 定位缓存，文件按实际 SHA-256 命名。缓存命中时会核对官网的 `Last-Modified`、`Content-Length`、APK 摘要和已登记摘要；信息缺失或变化时重新下载。
5. `compat-checker` 调用 Android 模块共用的 `compat-core`。正式 profile 解析与未知候选分析共用 `HookMethodMatcher` 对锚点、参数/返回形状和唯一性的判断；未知版本使用最近的较早正式 profile，正式版本还要求方法描述符与登记值完全一致。
6. 未知版本只有在基线中所有 Hook 都标记 `safeForForwardInference: true` 且每个 Hook 唯一匹配时，才会生成候选 profile 建议。未标记、缺失、形状变化或多重命中都会进入 `NEEDS_HOOK_REVIEW`，不会猜测 Hook 目标。

## 检查结果

每次成功发现候选都会生成 `candidate-report.json`，包括候选包名、版本、ABI、签名、APK SHA-256、来源、逐 Hook 结果、基线版本、回归版本、流水线状态、阻塞原因，以及安全时生成的候选 profile。报告作为 14 天 artifact 上传，状态和 Hook 诊断也会写入 Actions job summary；最终状态通过 `latest` job output `pipeline_status` 暴露给后续步骤。

候选经过静态检查和回归后，最多到 `STATIC_VERIFIED_PENDING_RUNTIME`。状态不会由 CI 改写为正式支持；开发者仍需在本地 AVD 完成登录界面冒烟，并按设计流程提交、合并 profile。当前工作流不创建 Issue、Pull Request 或候选分支，也不改动正式支持清单。

候选发现或下载失败会生成 `FETCH_FAILED` 报告；profile 清单或回归窗口无效会生成 `BASELINE_INVALID`；已登记回归失败会生成 `STATIC_REGRESSION_FAILED`。未知候选需要人工分析时，`NEEDS_HOOK_REVIEW` 是可供流水线继续分支处理的结果，不会被误报为 `UNKNOWN_BUILD`。

在仓库的 **Actions** 页面选择 **Check WeChat compatibility**，再点 **Run workflow** 即可运行。工作流不使用签名 Secrets，不启动 AVD，也不安装 Magisk/LSPosed。
