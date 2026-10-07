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

候选经过静态检查和回归后，最多到 `STATIC_VERIFIED_PENDING_RUNTIME`。状态不会由 CI 改写为正式支持；开发者仍需在本地 AVD 完成登录界面冒烟，并按设计流程提交、合并 profile。未登记构建在主分支上继续进入 Codex 适配任务；已登记构建只检查现有 profile。Codex 成功的改动进入 draft PR，候选 profile 保持 `static-verified`。

候选发现或下载失败会生成 `FETCH_FAILED` 报告；profile 清单或回归窗口无效会生成 `BASELINE_INVALID`；已登记回归失败会生成 `STATIC_REGRESSION_FAILED`。未知候选需要人工分析时，`NEEDS_HOOK_REVIEW` 是可供流水线继续分支处理的结果，不会被误报为 `UNKNOWN_BUILD`。

在仓库的 **Actions** 页面选择 **Check WeChat compatibility**，再点 **Run workflow** 即可运行。工作流不使用签名 Secrets，不启动 AVD，也不安装 Magisk/LSPosed。

## Codex 适配

`Run workflow` 中的 `run_codex` 默认为开启，只在私有仓库主分支发现可信的未登记构建时调用模型。关闭该选项可只运行静态检测。每个构建以版本码和完整 APK SHA-256 创建一次 Issue 记录；已有记录即跳过，失败或超时不会自动再次调用模型。任务串行运行，固定使用 `gpt-6-luna` 和 `xhigh`，关闭多代理能力，不自动升级模型。不设置模型进程或适配 job 的额外时间上限；任务仍受 GitHub Actions 平台限制，单次适配的订阅消耗取决于实际工作量。

模型在隔离 checkout 中检查真实 APK，可使用 jadx。控制器拒绝修改既有 profile、检查器、脚本、工作流和构建配置。新增 profile 必须使用已校验的身份和来源，状态只能为 `static-verified`。候选和最多两个较早正式支持版本分别经过共用检查器；核心测试、模块测试和 debug APK 构建通过后才发布 draft PR，并把 Issue 状态更新为 `WAITING_LOCAL_RUNTIME`。模型失败或静态检查失败时，Issue 和结果报告停留在 `NEEDS_HOOK_REVIEW`。

PR 分支包含可用于本地 AVD 冒烟的静态适配。完成登录界面冒烟后在 PR 中记录结果，将 profile 更新为 `runtime-verified-local`，审阅合入主分支后再由兼容检测确认 `FORMALLY_SUPPORTED`。

## 订阅认证配置

此流程使用 ChatGPT 管理的 Codex 登录，不使用 OpenAI API Key；它消耗订阅中的 Codex 用量。仅在可信私有仓库使用。需要两个 Actions Secrets：

| Secret | 用途 |
|---|---|
| `CODEX_AUTH_JSON` | CI 独立登录生成的 managed ChatGPT 凭据 |
| `CODEX_AUTH_WRITE_TOKEN` | 将 Codex 自动刷新后的凭据写回 Secret |

为写回创建 fine-grained GitHub token，只选择此仓库，授予仓库 **Secrets: Read and write** 权限；无需给这个 token 代码写入或 PR 权限。将其录入 Secret：

```sh
gh secret set CODEX_AUTH_WRITE_TOKEN --repo NKU100/WeChatPad
```

然后执行独立登录脚本，在浏览器中完成 device-code 登录。脚本使用临时 `CODEX_HOME`，上传后删除本地临时凭据，避免和桌面会话共用刷新状态：

```sh
bash scripts/setup_codex_ci_auth.sh NKU100/WeChatPad
```

runner 在模型调用前恢复凭据，之后即使模型失败也写回刷新后的文件，并在静态验证前删除 runner 上的凭据。写回 token 不传给模型进程。原始模型输出、登录凭据和会话目录不上传 artifact。凭据失效或 token 到期需要重新配置；不得通过自动重复适配来尝试修复登录。

还需在仓库 Actions 设置中开启 **Allow GitHub Actions to create and approve pull requests**。GitHub 将创建与审批放在同一个开关；此流水线只创建 draft PR，不提交审批或合并。draft PR 发布使用权限受限的 `GITHUB_TOKEN`；由该 token 创建的 PR 通常不会自动触发其他 workflow，因此发布后显式手动触发构建 workflow。

参考：[OpenAI managed-auth CI 指南](https://learn.chatgpt.com/docs/auth/ci-cd-auth)、[GitHub Secret 写入权限](https://docs.github.com/en/rest/actions/secrets#create-or-update-a-repository-secret)。
