# WeChatPad 设计说明

状态：修订待审阅

## 目标

构建 LSPosed 模块 `io.github.nku100.wechatpad`，为微信提供平板登录入口，以便用户尝试在已有手机之外登录同一账号。模块只改变微信客户端的平板登录表现，不承诺微信服务器一定允许多个移动设备会话长期并存。

首批兼容目标为微信 8.0.69 和 8.0.79：8.0.69 是新版平板判断特征出现前的最近版本，8.0.79 是当前版回归目标。两版共用 Hook 回调，但平板判断目标解析特征不同；仅混淆导致的方法描述符变化不作为选择依据。兼容清单保留所有已正式支持的构建；每次候选适配只对最新三个相关构建执行真实 APK 静态回归，较早构建不因退出回归窗口而自动移除支持记录。

### 首批版本选择依据

WeChatTablet 提交 [`7f53c39`](https://github.com/Xposed-Modules-Repo/top.hookvip.wxtablet/commit/7f53c39ca271454c699a39f48174231e5bde4b7e) 将平板判断的定位特征从 `Lenovo TB-9707F` 改为 `inTabletEnv, no tablet condition matched, return false`，并注明适用于 8.0.78 及以上。官方 APK 的静态 DEX 检查显示，新特征在 8.0.69 中不存在，到 8.0.70 已出现在完整平板判断方法中；8.0.69 需要旧特征。8.0.78 中旧特征位于只判断 Lenovo 机型的辅助方法，沿用旧规则会定位错方法。因此，8.0.69 与 8.0.79 是最近一组需要登记不同平板判断定位特征的版本。登录入口仍通过同一特征查找，两版使用相同的 Hook 回调动作。模块与 CI 共用解析器代码，按构建读取各自登记的特征数据。

| 微信版本 | 平板模式判断 | 登录入口可见性 |
| --- | --- | --- |
| 8.0.69 (3040) | `Lcom/tencent/mm/ui/qj;->B(Lfd5/n0;)Z` | `Lg21/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V` |
| 8.0.79 (3200) | `Lcom/tencent/mm/ui/ok;->C(Lpv5/w0;)Z` | `Lfb1/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V` |

样本身份记录：8.0.69 的 [腾讯 CDN ARM64 APK](https://dldir1v6.qq.com/weixin/android/weixin8069android3040_0x2800455a_arm64.apk)，SHA-256 为 `e4da5809f2b3305e375db38897a4082085adc6b51182fa807813c4dda1c3a948`；8.0.79 的 [腾讯 CDN ARM64 APK](https://dldir1v6.qq.com/weixin/android/weixin8079android3200_0x28004f30_arm64.apk)，SHA-256 为 `5feb100337981467fd257c3ad66bb171f54a69d2579b2ecc70d5a628db8e7282`。两者签名证书 SHA-256 均为 `0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c`。

## 范围与边界

- 首版实现完成平板登录所需的最小 Hook，不复刻 WeChatTablet 的无关功能，也不依赖或捆绑第三方微信模块。
- 只有包名、版本构建身份、APK 签名和 Hook 解析结果均通过验证的微信构建，才列为正式支持版本。
- 未知、缺少特征或解析到多个候选的构建一律不安装 Hook，并记录可诊断原因。
- AVD 运行时冒烟由开发者在本地专用 AVD 执行，只验证模块注入、微信启动、登录入口和二维码登录页面；不执行真实登录或验证服务器会话。
- GitHub 构建 CI 只构建模块 APK 并提供下载，不下载或检查微信 APK。后续兼容检测 CI 才下载候选微信 APK 并执行静态兼容检查；两类 CI 都不启动 AVD 或安装 LSPosed。
- 首版不启用每日计划任务，不要求付费 API，也不自动合并兼容更新。

## 兼容核心

`compat-core` 是纯 Kotlin/JVM 库，不依赖 Android、LSPosed 或微信类。它负责：

1. 校验微信构建身份及已登记的兼容目标。
2. 根据兼容清单为每个构建登记的 Hook 特征定义，使用同一套规则对 DEX 方法事实进行候选匹配。
3. 要求 profile 恰好声明一个 `tablet` Hook 和一个 `login` Hook；缺失、重复或多余的 Hook id 都作为无效 profile 拒绝。
4. 校验方法结构、参数和返回类型，并要求每个 Hook 恰好命中一个候选。
5. 输出可序列化的结果：兼容、未支持、profile 无效、特征缺失、签名不匹配、候选不唯一或 APK 身份不符。

Android 模块运行时与兼容检查器必须调用同一份 `compat-core` 代码和同一份按构建登记的 Hook 特征数据。`HookMethodMatcher` 是锚点、参数/返回形状和唯一性判断的单一实现，由正式 profile 解析和未知候选分析共同调用；候选分析额外检查前向推断标记，正式解析额外精确比较登记描述符。平台侧只提供 APK/DEX 数据及运行时可 Hook 的方法句柄。选择 DEX 读取方式时，先验证同一事实提取实现能否同时在 Android 运行时和兼容检测 CI 使用；若必须有平台适配器，适配器只负责读取数据，核心匹配规则仍保持共用。模块构建 CI 不执行这项兼容检查。

## 运行时行为

微信进程启动后，模块识别包名与构建身份，取得 DEX 方法事实并调用兼容核心。仅当平板模式 Hook 和登录入口 Hook 都唯一解析、签名校验通过时，才同时安装 Hook；任一失败则不安装任何 Hook，避免半启用状态。

libxposed API 102 的 `onPackageLoaded` 在目标 `Application` 创建前执行，只提供 `ApplicationInfo`，不能直接读取 `PackageInfo` 的版本码和签名信息。首次运行按已安装基础 APK 的 SHA-256 精确匹配登记 profile；静态校验已将该 APK 内容与签名证书摘要绑定。运行时只启用静态校验或本地运行时验证过的 profile。解析成功后，缓存按 APK 路径、大小、修改时间、UID、共享解析器版本和功能规则版本索引。后续启动先校验该安装指纹及缓存键对应的登记 profile，未命中时重新计算 APK 哈希。未知 APK 在创建临时 Hook 前退出。

成功解析结果可以缓存。缓存身份包含微信 APK 哈希、签名、版本码、共享解析器版本及功能规则版本；微信 APK 或其中任一规则版本改变时必须失效并重新解析。解析器匹配行为变化时必须提升解析器版本。缓存损坏或版本不明时重新解析，不能将缓存错误降级为宽松匹配。

## 兼容清单与证据

`compatibility/targets.json` 登记每个微信构建的包名、版本名、版本码、渠道/ABI、APK SHA-256、签名证书摘要、Hook 特征版本及验证状态。每个 Hook 还登记 `safeForForwardInference`，只有已验证可跨构建沿用的锚点才允许静态自动推断；默认和未标记值均为 `false`。状态至少区分：

- `static-verified`：APK 来源、哈希、签名和共用解析器检查通过。
- `runtime-verified-local`：开发者在本地专用 AVD 上确认模块注入并完成登录界面冒烟；PR 描述记录微信版本、AVD 系统镜像和结果。

静态通过不等同于正式兼容。正式支持状态要求候选 profile 通过规定的静态回归、本地 AVD 登录界面冒烟通过，并且包含该 profile 的 PR 已合并到主分支。GitHub CI 不负责产生本地运行时验证状态。已正式支持的较早构建保留在清单中，但常规候选 CI 不重复扫描整个历史版本矩阵。

2026-10-05，本地 AVD 已完成 8.0.69 与 8.0.79 的无模块基线及 WeChatPad 登录流程冒烟；两个版本均显示平板登录入口并能进入二维码页面。二维码未扫描，未执行真实登录。环境和逐版本结果见 [本地运行时冒烟记录](../validation/wechatpad-local-smoke.md)。

## CI 与后续适配

### 构建 CI

推送、Pull Request 和手动触发时构建模块 APK，并将 APK 作为 GitHub Actions artifact 提供下载。Pull Request 使用 runner 的临时 debug 签名；主分支的推送和手动构建在四项签名 Secrets 齐全时使用专用于 WeChatPad 的稳定密钥，密钥不能提交到仓库。四项 Secrets 全缺席时警告并退回 runner 的 debug 密钥；只配置了部分 Secrets 时构建失败。尚未配置稳定密钥期间，不同 runner 构建的签名可能不同，更新模块时需卸载旧版再安装。此 workflow 不下载或检查微信 APK，不运行兼容检查，也不启动 AVD、不安装 Magisk/LSPosed。暂不启用定时构建。

### 后续兼容检测 CI

兼容检测 workflow 仅由 `workflow_dispatch` 手动触发，不设置每日计划。它从微信官网首页发现最高版本 ARM64 APK 候选；未知候选加上版本码最高的两个已正式支持构建，候选已登记时检查最近三个已正式支持构建。已登记 APK 以 SHA-256 为缓存键；未知候选以官方直链 SHA-256 定位缓存，APK 文件按实际 SHA-256 命名，并保存 `Last-Modified`、`Content-Length` 与摘要以校验新鲜度和完整性。所有下载都限制为 HTTPS `dldir1v6.qq.com/weixin/android/`。

每个构建调用与模块共用的 `compat-checker` 和 `compat-core`。报告包含身份、逐 Hook 解析结果、回归版本和流水线状态，并上传 `candidate-report.json` artifact、写入 Actions summary 和 job output。未知候选只在所有必需 Hook 都由显式标记为可前向推断的锚点唯一定位时生成 profile 建议；否则进入 `NEEDS_HOOK_REVIEW`，不猜测 Hook 目标。当前阶段不自动改代码、不创建 Issue 或 PR。静态检查通过后仍需本地 AVD 验收。操作说明见 [兼容检测 CI](../validation/compatibility-check-ci.md)。

### 自动适配流水线

候选流水线状态与模块运行时的 `UNKNOWN_BUILD` 分开。`UNKNOWN_BUILD` 只表示当前安装版本没有可用的正式 profile；流水线状态记录候选处理进度。每次运行输出机器可读的 `candidate-report.json` artifact，包含候选身份、来源与哈希、逐 Hook 结果、当前流水线状态、阻塞原因和本次实际检查的版本；同时写入 GitHub Actions job summary，并通过 job output 驱动后续步骤。成功的候选由 draft PR 持久化；进入 `NEEDS_HOOK_REVIEW` 的候选按版本和 APK SHA-256 创建或更新一个 GitHub Issue，并附诊断 artifact 链接，作为人工处理队列。artifact、Issue 和 PR 都不是正式支持清单。

流水线按以下状态推进：

```text
DISCOVERED
  -> APK_VERIFIED
  -> ADAPTATION_RUNNING
  -> STATIC_VERIFIED_PENDING_RUNTIME
  -> WAITING_LOCAL_RUNTIME
  -> LOCAL_RUNTIME_VERIFIED
  -> FORMALLY_SUPPORTED
```

下载或完整性失败进入 `FETCH_FAILED`；包名、ABI 或签名不符进入 `IDENTITY_REJECTED`；基线 profile 无效进入 `BASELINE_INVALID`；Hook 特征缺失、方法形状无法匹配或候选不唯一进入 `NEEDS_HOOK_REVIEW`；静态回归失败进入 `STATIC_REGRESSION_FAILED`；本地冒烟失败进入 `RUNTIME_REJECTED`。失败状态附诊断，不得转成正式支持。

静态检查器先使用模块共享的 `compat-core` 识别候选 APK。每个 Hook 特征都必须明确声明 `safeForForwardInference`；只有经验证可跨构建沿用的稳定特征才能设为 `true`。未显式标记的特征即使唯一命中，也只报告候选描述符并进入人工检查，避免把同一字符串在新版中的辅助方法误认为 Hook 目标。所有必需 Hook 都能从允许前向推断的稳定特征唯一定位时，适配步骤可以从实际 DEX 事实生成候选构建 profile，包括更新唯一命中的方法描述符。特征缺失、参数/返回形状变化或多重命中时，不推测 profile；由 Codex 适配 worker 在隔离分支提出代码或 profile 改动。自动或模型生成的改动都必须进入 draft PR，并再次通过同一兼容检查器和模块构建 CI；不得直接提交到主分支或自动合并。

常规适配回归窗口最多包含三个构建：若候选是新版本，则为候选 APK 加上 `compatibility/targets.json` 中版本码最高的两个已正式支持构建；若候选已登记，则取按版本码排序后的最新三个正式支持构建。版本重复时去重，登记版本不足三个时检查全部可用版本。窗口外的旧版 profile 仍保留，但不属于每轮候选 CI 的静态回归范围。

Codex 自动适配 worker 的运行环境和授权方式尚未确定；当前静态兼容检测不依赖 worker。只有进入自动处理 `NEEDS_HOOK_REVIEW` 的下一阶段时，才需要确定 worker 如何运行及如何获得授权。worker 的接口边界限定为：接收候选诊断，在隔离分支提出代码或 profile 改动，并创建 draft PR；所有改动仍经过同一静态检查，不能直接提交主分支或自动合并。环境或授权暂不可用时，候选停留在 `NEEDS_HOOK_REVIEW`。

静态回归通过后，候选进入 `WAITING_LOCAL_RUNTIME`。开发者在本地 AVD 对候选微信执行登录界面冒烟，并把结果记录到 PR；通过后将 profile 状态更新为 `runtime-verified-local`。只有该 PR 合并进主分支后，流水线才输出 `FORMALLY_SUPPORTED`。每日触发暂不启用；初始自动适配仍由 `workflow_dispatch` 驱动。OpenAI 用量限制或 worker 故障都不能绕过本地冒烟和 PR 合并门槛。

## 验收

1. 共用兼容核心的测试覆盖：唯一命中、缺少或重复 Hook id、零命中、多重命中、方法签名不符、未知构建、错误 APK 身份和缓存失效。
2. 8.0.69 与 8.0.79 的 APK 均通过身份校验；桌面检查器与运行时使用同一份按构建登记的特征数据和匹配结果。
3. 开发者在本地专用 AVD 上对两版完成运行时冒烟，确认模块注入、微信不崩溃、登录入口出现且可进入二维码登录页面；PR 记录版本、镜像和结果。
4. 一次新增版本适配的回归流程证明候选及回归窗口内的构建均可解析；候选未通过本地 AVD 或 PR 未合并时，不得输出 `FORMALLY_SUPPORTED`。
5. 使用真实 8.0.78 和 8.0.79 APK：先以共用检查器核验临时 8.0.78 profile，再分别用仅含 8.0.69、以及含 8.0.69 和 8.0.78 的临时清单诊断 8.0.79。临时清单只模拟静态 pipeline 输入，不声称 8.0.78 已完成本地运行时验证，也不进入正式支持记录。
6. 每轮候选 CI 最多静态检查三个构建，并明确在报告中记录被选中的版本；窗口外的正式支持 profile 保留在清单中，但不声称本轮已重新验证。
7. 流水线状态同时出现在机器可读报告、Actions summary 和 job output；静态候选通过但尚未本地验收时不得输出 `FORMALLY_SUPPORTED`。
8. GitHub 构建 CI 可从干净检出构建模块 APK 并将其作为 artifact 提供下载；不下载微信 APK、不执行兼容分析，也不依赖 AVD 或 LSPosed 环境。兼容检测 CI 与构建 CI 分离。

## 实施顺序

1. 建立共用兼容核心和 JVM 测试，再验证 DEX 事实提取在 Android 与桌面 CI 的可复用边界。
2. 获取并校验 8.0.69、8.0.79 APK，建立两版兼容清单与各自的平板判断定位特征。
3. 实现最小运行时 Hook，完成两版 AVD 登录界面冒烟及旧版回归。
4. 增加推送、PR、手动触发的构建 CI。
5. 为未登记候选增加静态状态模型、逐 Hook 诊断报告和共用匹配逻辑；使用真实 8.0.79 APK，分别以仅有 8.0.69、以及 8.0.69 加 8.0.78 的临时清单验证状态输出，不改正式支持清单。
6. 增加候选 profile 生成和 draft PR；每轮静态回归最多检查最近三个构建，并记录实际选择的版本。
7. 确定 Codex 适配 worker 的执行环境和授权方式后，再实现 worker；只在静态检查无法安全自动适配时派发任务，模型改动仍走 draft PR 和同一套静态检查。
8. 本地 AVD 验收通过后更新 profile 状态并合并 PR，只有主分支上的已合并条目才进入 `FORMALLY_SUPPORTED`。
9. 每日触发留待单独启用。

## 首阶段运行时验证结论

- Android 运行时与桌面检查器共用同一个 DEX 事实读取器和兼容解析器；8.0.69、8.0.79 的静态检查和运行时日志均解析出清单登记的两个唯一方法。
- 官方 LSPosed 2.2.0（7854）在 API 37 AVD 上加载 API 102 模块；两个版本都记录了 `installed 2 WeChat hooks`，微信推送子进程被跳过。
- 从 8.0.69 更新到 8.0.79 后，安装指纹变化导致缓存未命中并重新解析；随后再次冷启动记录缓存命中。
- AVD 登录入口及二维码页面的逐版本冒烟结果见 [本地运行时冒烟记录](../validation/wechatpad-local-smoke.md)。
