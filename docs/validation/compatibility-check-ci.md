# 兼容检测 CI

工作流 `Check WeChat compatibility` 每天北京时间 10:23（UTC 02:23）自动触发，也可手动运行。默认从微信官网首页发现最高版本的 ARM64 APK 候选。自动和手动触发均只检查官网最新 ARM64 APK，不提供指定版本入口。下载后以 APK 内实际版本、官方签名和 SHA-256 为准。已正式支持且 APK 摘要未变化时提前结束，不启动静态矩阵、构建、Codex 或 AVD；手动选中 `force_recheck` 可重新静态检查。需要分析时再按候选版本选择静态回归窗口：新候选加上版本码最高的两个已正式支持旧版，已支持候选检查候选本身和最多两个较早的正式支持版本。报告列明本次实际检查的版本，历史 profile 保留。

## 检查流程

1. 已登记 APK 只允许使用清单中的 HTTPS 腾讯 CDN 地址 `dldir1v6.qq.com/weixin/android/`，并以预期 APK SHA-256 为缓存键。
2. 最新候选从 `https://weixin.qq.com/` 首页发现。脚本只接受官网列出的腾讯 CDN ARM64 直链，并选择唯一的最高版本；没有候选、多个并列候选或页面结构变化都会失败，不切换到第三方来源。
3. 候选版本码用于选择最多两个较早的 `runtime-verified-local` 或 `runtime-verified-hosted` profile；候选自身另行检查，因此每轮最多覆盖三个不同版本。
4. 候选 APK 以官方直链 SHA-256 定位缓存，文件按实际 SHA-256 命名。缓存命中时会核对官网的 `Last-Modified`、`Content-Length`、APK 摘要和已登记摘要；信息缺失或变化时重新下载。
5. `compat-checker` 调用 Android 模块共用的 `compat-core`。正式 profile 解析与未知候选分析共用 `HookMethodMatcher` 对锚点、参数/返回形状和唯一性的判断；未知版本使用最近的较早正式 profile，正式版本还要求方法描述符与登记值完全一致。
6. 未知版本只有在基线中所有 Hook 都标记 `safeForForwardInference: true` 且每个 Hook 唯一匹配时，才会生成候选 profile 建议。未标记、缺失、形状变化或多重命中都会进入 `NEEDS_HOOK_REVIEW`，不会猜测 Hook 目标。

## 检查结果

每次成功发现候选都会生成 `candidate-report.json`，包括候选包名、版本、ABI、签名、APK SHA-256、来源、逐 Hook 结果、基线版本、回归版本、流水线状态、阻塞原因，以及安全时生成的候选 profile。报告作为 14 天 artifact 上传，状态和 Hook 诊断也会写入 Actions job summary；最终状态通过 `latest` job output `pipeline_status` 暴露给后续步骤。

候选经过静态检查和回归后，最多到 `STATIC_VERIFIED_PENDING_RUNTIME`。状态不会由 CI 改写为正式支持；开发者仍需在本地 AVD 完成登录界面冒烟，并按设计流程提交、合并 profile。未登记构建在主分支上继续进入 Codex 适配任务；已登记构建只检查现有 profile。Codex 成功的改动进入 draft PR，候选 profile 保持 `static-verified`。

候选发现或下载失败会生成 `FETCH_FAILED` 报告；profile 清单或回归窗口无效会生成 `BASELINE_INVALID`；已登记回归失败会生成 `STATIC_REGRESSION_FAILED`。未知候选需要人工分析时，`NEEDS_HOOK_REVIEW` 是可供流水线继续分支处理的结果，不会被误报为 `UNKNOWN_BUILD`。

在仓库的 **Actions** 页面选择 **Check WeChat compatibility**，再点 **Run workflow** 即可运行。静态检测不使用签名 Secrets；新候选的后续托管冒烟会安装 Magisk/LSPosed 并启动 AVD。

## 普通构建验证

`Build module APK` 在 push、PR 和手动构建中运行核心、检查器、应用及 Python 流水线单元测试，检查模块元数据与打包内容，并对版本码最高的最多三个正式支持构建做真实 APK 静态回归。每次代码构建都会重新检查，已支持状态不会跳过回归。APK 仅从已登记的官方 URL 获取，按 SHA-256 缓存，每次使用前重新校验摘要；检查失败阻止构建通过并上传每个构建的日志和结果报告。

普通构建和适配控制器共用 `scripts/ci/static_regression.py` 的下载校验及检查器调用。适配仍覆盖候选加最多两个旧版，使用预下载 APK 离线检查。普通构建不调用 Codex 或 AVD。单元测试验证解析、拒绝、缓存和 Hook 注册等逻辑；真实 APK 静态回归验证目标解析；实际注入和界面行为由动态冒烟验证。

## 单版本运行验证

`Validate WeChat runtime` 用于重放一个已支持版本的构建和托管 AVD 验证。它选择官网最新 APK；若该精确 APK 尚未登记并完成运行验证，则停止并提示先运行兼容适配，不自动换成已支持的其他版本。

`Run WeChat runtime smoke` 的独立手动入口也检查官网最新 APK，使用同一套候选选择、官方下载和摘要校验逻辑。由适配流程调用时直接使用已经静态验证的精确候选产物。每次运行只启动一个版本的动态冒烟，静态回归仍最多覆盖三个版本。运行验证入口不调用 Codex、不创建 PR、不更新正式支持状态。

## Codex 适配

`Run workflow` 中的 `run_codex` 默认为开启，只在主分支手动或定时运行中发现可信的未登记构建时调用模型。关闭该选项可只运行静态检测。每个构建以版本码和完整 APK SHA-256 维护 Issue 记录，只认可 `github-actions[bot]` 创建且带 `wechatpad-adaptation` 标签的记录，排除 PR。旧的机器人记录会补上标签，不重复适配。已有记录默认跳过，失败或超时不会自动再次调用模型。手动开启 `retry_adaptation` 可复用原 Issue 重试失败、取消、超时或跳过的适配；仍在执行的任务不能重试。显式重试也可重新适配运行验证失败或等待运行验证的候选；保留旧 PR，新尝试使用按 workflow run 区分的分支和草稿 PR。未勾选重试时仍跳过。任务串行运行，通过 Codex app-server 为每个构建创建一个 Goal，固定使用 `gpt-6-luna` 和 `xhigh`，关闭多代理能力，不自动升级模型。Goal 默认总 Token 预算为 500000，手动入口可用 `goal_token_budget` 调整为正整数；达到预算或用量限制、明确受阻、同一验收错误连续出现三次时停止。每轮结束后控制器暂停 Goal 并等待线程空闲，再独立验证改动；失败原因反馈给同一线程继续修正，不创建新适配任务。模型标记完成不能绕过独立验收。不设置模型进程或适配 job 的额外时间上限；任务仍受 GitHub Actions 平台限制，单次适配的订阅消耗取决于实际工作量。

托管 runner 安装发行版 bubblewrap，并加载可用的专用 AppArmor profile。调用模型前通过同一 app-server 执行 workspace-write 沙箱命令，检查候选文件可读和工作目录可写；检查失败时不创建 Goal、不消耗模型 Token。模型只获得无历史、无远端的独立构建源码 checkout、原始 APK 和身份报告；不提供历史文档和检查器推导的 Hook。测试使用合成符号。外层 bubblewrap 仅挂载构建源码、独立用户目录、认证目录和工具；Gradle 只复制依赖与 wrapper 缓存，不暴露原仓库、报告、项目构建缓存和控制器状态。预检验证原仓库与控制器状态不可读。模型可使用 jadx 检查真实 APK。控制器拒绝修改既有 profile、检查器、脚本、工作流和构建配置。新增 profile 必须使用已校验的身份和来源，状态只能为 `static-verified`。候选和最多两个较早正式支持版本分别经过共用检查器；核心测试、模块测试和 debug APK 构建通过后才发布 draft PR，并把 Issue 状态更新为 `WAITING_RUNTIME`。模型失败或静态检查失败时，Issue 和结果报告停留在 `NEEDS_HOOK_REVIEW`。

PR 分支包含静态适配。流水线随后自动执行托管 AVD 登录界面冒烟，通过后记录结果并将候选更新为 `runtime-verified-hosted`；审阅合入主分支后再由兼容检测确认 `FORMALLY_SUPPORTED`。本地 AVD 可用于失败诊断或补充验证。

## 订阅认证配置

此流程使用 ChatGPT 管理的 Codex 登录，不使用 OpenAI API Key；它消耗订阅中的 Codex 用量。仅在主分支手动或定时触发的可信工作流中使用；PR 或 fork 不可触发认证恢复。需要两个 Actions Secrets：

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

runner 在模型调用前恢复凭据，Goal 结束后即使模型失败也写回刷新后的文件，删除认证文件，再执行发布前的最终独立验收。写回 token 不传给模型进程。登录凭据和会话目录不上传 artifact。产物中的 `goal-diagnostics.json` 保留每轮验收结果、Goal 用量、模型最终说明及失败工具摘要；已知认证凭据和常见 Token 格式在写入前过滤。凭据失效或 token 到期需要重新配置；不得通过自动重复适配来尝试修复登录。

### 加密会话记录

仓库 Actions variable `CODEX_TRACE_RECIPIENT` 配置 age X25519 公钥（`age1…`），私钥只保存在本机，不放入仓库或 Actions。CI 安装 age，在调用模型前验证公钥。缺失、无效的公钥或加密工具故障会阻止模型启动。

控制器完整记录发给 app-server 的请求和收到的响应、通知，包括任务提示、工具调用及成功和失败命令的输出；每条 JSONL 记录包含 UTC 时间、方向和协议消息。记录不截断、不脱敏，直接通过管道送入 age 加密，不生成明文会话文件，也不写入 Actions 控制台或摘要。这里的完整记录指 app-server 对外提供的协议事件，不包含未公开的模型内部内容、认证文件、CLI 会话目录或原始 stderr。

模型成功或失败后，完成加密的 `session.jsonl.age` 和现有诊断文件一起作为 `wechatpad-codex-adaptation` artifact 保存 14 天。加密失败会删除未完成密文；上传清单仅包含完成后的文件。runner 被强制终止时可能没有可恢复的完整记录。任何取得 artifact 的人只能获得密文，runner 在处理事件时仍可接触明文；仅使用可信主分支工作流。

本机安装 age 后，在仓库外用私钥解密，再交给本机 Codex 分析：

```sh
umask 077
age --decrypt --identity ~/.config/wechatpad/ci-trace.agekey \
  --output session.jsonl session.jsonl.age
```

私钥丢失后无法解密旧记录，应在可信的本地存储中备份。更换公钥只影响后续运行，旧 artifact 仍需原私钥。生成新密钥可用 `age-keygen --output <私钥文件>`，公钥可用 `age-keygen -y <私钥文件>` 提取。

还需在仓库 Actions 设置中开启 **Allow GitHub Actions to create and approve pull requests**。GitHub 将创建与审批放在同一个开关；此流水线只创建 draft PR，不提交审批或合并。draft PR 发布使用权限受限的 `GITHUB_TOKEN`；由该 token 创建的 PR 通常不会自动触发其他 workflow，因此发布后显式手动触发构建 workflow。

参考：[OpenAI managed-auth CI 指南](https://learn.chatgpt.com/docs/auth/ci-cd-auth)、[GitHub Secret 写入权限](https://docs.github.com/en/rest/actions/secrets#create-or-update-a-repository-secret)。

## 托管运行时验证

兼容检测由主分支手动或定时触发。Codex 适配的静态检查和构建成功后，同一次运行调用 `runtime-smoke.yml`，复用已校验的微信 APK 和模块 APK。托管 AVD 使用固定系统镜像、修补 ramdisk、Magisk 和官方 LSPosed；工作流安装框架、启用模块并验证无模块基线。

通过标准为模块注入成功、Hook 安装无错误、Phone & Tablet 登录入口出现，且可进入稳定的二维码页。无需扫码、登录账号或验证双设备服务器会话。

成功输出 `RUNTIME_VERIFIED`，更新候选为 `runtime-verified-hosted`，记录 PR 和 Issue；合并后才正式支持。失败输出 `RUNTIME_REJECTED`，保持草稿 PR，并上传截图、UI 树和日志。取消或跳过时保留 `STATIC_VERIFIED_PENDING_RUNTIME`，Issue 标记为 `WAITING_RUNTIME`，不发表运行失败评论，也不晋级候选。PR 被改动时拒绝使用旧运行结果晋级。托管冒烟串行执行，最多排队 100 次运行，后来的运行不会替换已有等待任务。

`runtime-validation.yml` 可手动用官网最新且已登记的精确 APK 重放构建、静态检查、跨任务 artifact、托管冒烟和结果判定；不调用 Codex，不创建 PR 或修改正式支持清单。

勾选 `rebuild_ramdisk` 可同时从官方输入重建 root ramdisk，校验与 Release 产物逐字节一致，再执行冒烟。制作步骤及本地命令见 [AVD root ramdisk 制作](../environment/ramdisk-build.md)。

会话记录另按最多 32 条事件或 1 MiB 明文缓冲划分为独立 age 密文分段，不落地明文。
可信 action 在模型运行期间每分钟上传 `wechatpad-codex-live-*` artifact，包含本轮新增的完整密文分段与 runner 的内存、磁盘、进程名和 cgroup 计数；上传凭据不会传给模型。
正常结束仍保留完整 `session.jsonl.age`。异常结束时按分段文件名排序分别解密即可恢复已上传的前缀，未形成完整分段或尚未上传的尾部可能丢失。
SIGTERM/SIGINT 会触发控制器诊断和加密收尾；SIGKILL、runner 丢失或平台终止整个 action 时，只能依靠此前已上传的快照，不保证最后一次上传成功。

JADX 启动器使用共享文件锁串行执行反编译，JVM 堆上限为 4 GiB、反编译线程数默认为 2，避免多个反编译进程按整机内存比例同时分配堆。
实时快照同时读取实际进程的 cgroup 内存计数，并尽力采集本轮内核日志和 runner 服务日志；服务日志可能包含凭据，只上传 `runner-logs.json.age` 密文，不上传原始内容。日志不可读时明确记录 `unavailable`。

适配 job 先启动单个临时 API 37.2 AVD（2 核、4 GiB 内存），用共用流程验证无模块时没有平板入口，并准备 Magisk、官方 LSPosed 和模块作用域。准备失败时不创建模型 Goal。
每轮生成临时 debug keystore，基线、模型构建和宿主验收通过 `WECHATPAD_DEBUG_KEYSTORE` 显式选择同一份密钥，避免不同 HOME 下默认 debug key 不一致；此密钥不用于正式发布。
运行报告从本次探测的新鲜 logcat 提取模块加载、兼容状态、Hook 安装及实际描述符，失败反馈直接提供这些观察。未观察到记录不等于证明注入失败；已安装 Hook 而入口缺失时，应重新核查所选方法的调用路径、提前返回和缓存。
模型沙箱通过工作区文件请求中转访问专用 ADB server，宿主控制器执行命令并返回原始输出；预检确认固定模拟器可访问。中转固定设备、限制设备命令和本地文件路径，外部网络仍关闭。禁网沙箱禁止 Unix socket 的 connect 调用，因此不让模型直接连接 ADB socket。
同一个 Goal 每轮依次通过静态检查、测试、构建和 AVD 行为验收。运行验收安装可信控制器保存的精确候选 APK 和本轮模块，验证两个 hook、平板入口和稳定二维码页面；失败证据复制到模型工作区，交回原会话修正。更换证据目录不会重置连续三次同类错误的停止计数。
通过这轮验收后才创建草稿 PR，随后原有独立 job 在新的干净 AVD 再次冒烟，只有该独立结果可以晋级 `runtime-verified-hosted`。运行中的诊断继续加密保存，适配 AVD 的普通失败证据单独上传为 `wechatpad-adaptation-avd`。
