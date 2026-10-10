# WeChatPad 本地适配实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 WeChatPad 首阶段本地实现，使同一 APK 事实读取器和兼容匹配核心同时服务于 Android 模块与桌面检查器，并在专用 AVD 上验证微信 8.0.69 和 8.0.79 的登录界面。

**Architecture:** 建立 `app`、纯 Kotlin/JVM `compat-core` 和 Kotlin/JVM `compat-checker` 三个 Gradle 子项目。`compat-core` 读取共享的 `compatibility/wechat/targets.json`，从共同的 DEX 事实读取器接收方法描述符、参数/返回类型和方法内字符串，再进行严格身份校验、唯一候选解析与缓存判定；Android 和桌面侧只负责提供 APK 身份与目标方法句柄。Android 模块使用官方 libxposed API 102；Hook 仅在两个目标均完成解析和反射解析后成组安装。

**Tech Stack:** 沿用 [NKU100/carrier-ims](https://github.com/NKU100/carrier-ims) 的现代 LSPosed 模块结构、AGP/API 版本和 Java 21 字节码目标；首轮工程固定使用 Gradle 9.8.0、Android Gradle Plugin 9.4.0、Kotlin Gradle Plugin/serialization plugin 2.4.20、官方 `io.github.libxposed:api:102.0.0`（`compileOnly`）、Google `com.android.tools.smali:smali-dexlib2:3.0.10`、Kotlin serialization JSON 1.11.0，以及 Android SDK `apkanalyzer`/`apksigner`。版本目录只记录稳定版的精确版本，不使用动态版本、快照或预览版；开始 Task 1 时再次核对上游是否发布了更新的稳定版，并同步更新 Gradle wrapper 和依赖版本目录。Android app 使用 AGP 9.4 内置 Kotlin 支持，不应用旧的 `org.jetbrains.kotlin.android` 插件；根构建显式固定 KGP 2.4.20，供兼容核心、检查器及序列化编译插件使用。模块使用 `minSdk=28`、`compileSdk=37` / minor 2，与本地 Android 17 AVD 对齐。

**Spec:** [2026-10-04-wechatpad-design.md](../specs/2026-10-04-wechatpad-design.md)

## Global Constraints

- 模块包名固定为 `io.github.nku100.wechatpad`。
- 首批目标固定为微信 8.0.69 (3040) 与 8.0.79 (3200)，两者都必须继续通过完整兼容矩阵。
- 8.0.69 平板判断特征使用 `Lenovo TB-9707F`；8.0.79 使用 `inTabletEnv, no tablet condition matched, return false`；登录入口两版均使用 `loginAsOtherDeviceBtn`。
- `compat-core` 的匹配与安全判定由桌面检查器和 Android 模块共同调用；解析到零个、多个或签名不符候选时不安装 Hook。
- 平板判断 Hook 在聊天调用栈中返回 `false`，其他调用场景返回 `true`；登录按钮仅在原本为 `GONE` 时改为 `VISIBLE`。
- Android 运行时和桌面检查器使用相同的 APK DEX 事实读取实现；平台代码不复制候选匹配逻辑。
- 运行时只在微信主进程执行身份检查和 DEX 解析，避免在推送、崩溃等辅助进程重复扫描。
- 本阶段在本地专用 AVD 上进行运行时冒烟；只验证模块注入、微信启动、登录入口和二维码登录页面，不进行真实登录。
- 本阶段不新增 GitHub Actions、每日任务或自动适配工作流；这些分别留给后续阶段。
- 只使用官方 LSPosed 发布版与官方 libxposed API；不依赖或捆绑 WeChatTablet、DexKit、YukiHookAPI 或其他微信模块。

## Review Focus

- 包名、版本码、签名或 APK 哈希任一不符时，预期行为是返回可诊断的不兼容结果且零 Hook；由 Task 2 的身份拒绝测试和 Task 3 的 APK 检查覆盖。
- 旧字符串在 8.0.78 的 Lenovo 专用辅助方法中仍可能出现，不能因此误认新版目标；由 Task 2 的多候选/签名测试和 Task 3 的 8.0.69、8.0.79 真 APK 检查覆盖。
- 多 DEX APK 或 DEX 指令中有非字符串引用时不能漏报或崩溃；由 Task 3 的多 DEX 与混合引用测试覆盖。
- 第二个 Hook 解析或注册失败时不能留下第一个 Hook；由 Task 4 的事务回滚测试覆盖。
- APK 更新、规则版本变化或损坏缓存后不能复用旧目标；由 Task 2 的缓存键测试和 Task 4 的更新后 AVD 冒烟覆盖。
- 未静态验证的 profile 或描述符与 profile 不一致的缓存不能启用 Hook；由 Task 4 的运行时解析测试覆盖。

---

### Task 1: 建立最小多模块工程

**Files:**
- Create: `settings.gradle.kts`
- Create: `build.gradle.kts`
- Create: `gradle/libs.versions.toml`
- Create: `gradle.properties`
- Create: `gradle/wrapper/gradle-wrapper.properties`
- Create: `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`
- Create: `compat-core/build.gradle.kts`
- Create: `compat-checker/build.gradle.kts`
- Create: `app/build.gradle.kts`
- Create: `app/src/main/AndroidManifest.xml`
- Create: `app/src/main/resources/META-INF/xposed/java_init.list`
- Create: `app/src/main/resources/META-INF/xposed/module.prop`
- Create: `app/src/main/resources/META-INF/xposed/scope.list`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/WeChatPadModule.kt`
- Test: Gradle project configuration and debug APK assembly.

**Interfaces:**
- Produces Gradle projects `:compat-core`, `:compat-checker`, and `:app`.
- `app` compiles against `io.github.libxposed:api:102.0.0` with `compileOnly`; module metadata sets `minApiVersion=102`, `targetApiVersion=102`, and static scope `com.tencent.mm`.
- `WeChatPadModule` is the registered `XposedModule` entry; this task only verifies framework loading metadata and does not yet install hooks.

- [x] **Step 1: Bootstrap the Gradle wrapper and write the failing metadata check**

Create the wrapper and minimal root settings/build files so Gradle can run, then add a verification task that asserts the Android application id is `io.github.nku100.wechatpad`, the static scope contains only `com.tencent.mm`, and packaged Xposed metadata declares API 102.

- [x] **Step 2: Run the check to verify the empty project fails**

Run: `./gradlew verifyModuleMetadata`
Expected: FAIL because the project and metadata files do not exist yet.

- [x] **Step 3: Create the three Gradle projects and official API metadata**

Use JDK 21 and the locally installed Android SDK. Use the Gradle 9.8.0 wrapper and the exact stable versions in the tech stack. Set `compileSdk=37`, `compileSdkMinor=2`, `buildToolsVersion=37.0.0`, and `minSdk=28`; use AGP built-in Kotlin in `app` and Kotlin/JVM 2.4.20 for the two shared modules. Register only the modern official libxposed entry and scope resources; do not add a launcher UI or unrelated app features.

- [x] **Step 4: Run project checks and assemble the module APK**

Run: `./gradlew verifyModuleMetadata :compat-core:test :compat-checker:test :app:assembleDebug`
Expected: PASS; `app/build/outputs/apk/debug/app-debug.apk` is produced with package `io.github.nku100.wechatpad`.

- [x] **Step 5: Commit the scaffold**

```bash
git add settings.gradle.kts build.gradle.kts gradle gradle.properties gradlew gradlew.bat compat-core compat-checker app
git commit -m "build: scaffold WeChatPad module"
```

### Task 2: Implement shared compatibility models, resolver, and cache contract

**Files:**
- Create: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/BuildIdentity.kt`
- Create: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/CompatibilityTarget.kt`
- Create: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/DexMethodFact.kt`
- Create: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/CompatibilityResult.kt`
- Create: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/CompatibilityResolver.kt`
- Create: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/ResolutionCache.kt`
- Create: `compat-core/src/test/kotlin/io/github/nku100/wechatpad/compat/CompatibilityResolverTest.kt`
- Create: `compat-core/src/test/kotlin/io/github/nku100/wechatpad/compat/ResolutionCacheTest.kt`
- Create: `compat-core/src/test/resources/targets-test.json`

**Interfaces:**
- `BuildIdentity(packageName: String, versionName: String, versionCode: Long, abi: String, apkSha256: String?, signerSha256: String)`; static APK evidence always supplies the hash, while Android package evidence may defer hashing until a cache miss.
- `DexMethodFact(descriptor: String, parameterDescriptors: List<String>, returnDescriptor: String, strings: Set<String>)`.
- `HookRule(id: String, stringAnchor: String, parameterDescriptors: List<String>, returnDescriptor: String, expectedDescriptor: String)`.
- `CompatibilityTarget(identity: BuildIdentity, featureRulesVersion: Int, hooks: List<HookRule>)`.
- `IdentityVerification` has `STATIC_APK` and `INSTALLED_PACKAGE` modes; the latter trusts exact package/version/ABI/signer evidence from Android PackageManager and compares an APK hash whenever one is available.
- `CompatibilityResolver.resolve(identity: BuildIdentity, verification: IdentityVerification, targets: List<CompatibilityTarget>, facts: List<DexMethodFact>): CompatibilityResult`.
- `ResolutionCacheKey(apkSha256: String, signerSha256: String, versionCode: Long, resolverVersion: Int, featureRulesVersion: Int)`; cache reads with malformed data or a nonmatching key return a miss. Bump `COMPATIBILITY_RESOLVER_VERSION` when shared matching behavior changes.
- `CompatibilityResult` exposes a typed status, a diagnostic reason, and resolved descriptors keyed by hook id. A target is compatible only when both required hook ids each resolve to exactly one matching method.

- [ ] **Step 1: Write resolver tests for the accepted and rejected inputs**

Cover unique hit, missing anchor, duplicate anchor candidates, parameter/return mismatch, wrong package, wrong version code, wrong signer, wrong APK hash, missing hash in `STATIC_APK` mode, unknown build, and the 8.0.78-style old-anchor collision. Assert that every rejected case has an empty resolved-hook map.

- [ ] **Step 2: Run resolver tests to verify they fail**

Run: `./gradlew :compat-core:test --tests '*CompatibilityResolverTest'`
Expected: FAIL because resolver types and implementation are absent.

- [ ] **Step 3: Add the shared model and strict resolver**

In `STATIC_APK` mode require an exact APK hash match. In `INSTALLED_PACKAGE` mode require exact package, version, ABI, and signing-certificate identity; if a SHA-256 is supplied, require it to match too. For each hook, filter methods by the registered string anchor and parameter/return descriptors, require exactly one result, then verify the recorded expected descriptor. Return a failure status on the first failed hook and expose no partial descriptors.

- [ ] **Step 4: Write and run cache tests**

Assert a cache hit for an identical key, misses when APK hash/signer/version/rule version changes, and a miss for truncated or invalid JSON. Implement atomic cache serialization in the pure Kotlin/JVM core.

- [ ] **Step 5: Run core tests and commit**

Run: `./gradlew :compat-core:test`
Expected: PASS with all resolver and cache cases.

```bash
git add compat-core
git commit -m "feat: add shared compatibility resolver"
```

### Task 3: Read APK DEX facts and verify the two target profiles

**Files:**
- Create: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/DexFactReader.kt`
- Create: `compat-core/src/test/kotlin/io/github/nku100/wechatpad/compat/DexFactReaderTest.kt`
- Create: `compat-core/src/test/resources/multidex-fixture.apk`
- Create: `compatibility/wechat/targets.json`
- Create: `compat-checker/src/main/kotlin/io/github/nku100/wechatpad/checker/Main.kt`
- Create: `compat-checker/src/main/kotlin/io/github/nku100/wechatpad/checker/ApkIdentityInspector.kt`
- Create: `compat-checker/src/test/kotlin/io/github/nku100/wechatpad/checker/ApkIdentityInspectorTest.kt`
- Modify: `compat-core/build.gradle.kts`
- Modify: `compat-checker/build.gradle.kts`

**Interfaces:**
- `DexFactReader.scan(apkFiles: List<File>, stringAnchors: Set<String>): List<DexMethodFact>` walks every `classes*.dex`, reads method descriptors and code string references, and retains only methods containing at least one requested anchor.
- `ApkIdentityInspector.inspect(apk: File): BuildIdentity` obtains package/version metadata via Android SDK `apkanalyzer`, ABI from APK native-library entries, signer via `apksigner`, and computes SHA-256 from the supplied APK.
- CLI command: `./gradlew :compat-checker:run --args='check --targets compatibility/wechat/targets.json --apk <apk-path>'`; exit 0 only for one fully compatible target and both hook resolutions.
- Target JSON contains the exact official CDN URLs, SHA-256 values, certificate digest, ABI, build identity, feature rule version, anchors, method shapes, and expected descriptors recorded in the spec.

- [ ] **Step 1: Write DEX reader tests using a small two-DEX fixture**

Use the committed `multidex-fixture.apk` containing `classes.dex` and `classes2.dex`. Assert that `scan` finds requested strings in both DEX files, returns the owning method descriptor and signature, ignores unrelated strings, and safely ignores instructions whose references are not strings.

- [ ] **Step 2: Run reader tests to verify they fail**

Run: `./gradlew :compat-core:test --tests '*DexFactReaderTest'`
Expected: FAIL because the reader is absent.

- [ ] **Step 3: Implement the shared DEX reader using Google’s smali dexlib2**

Use `com.android.tools.smali:smali-dexlib2:3.0.10`; keep the reader independent of Android and call this exact implementation from both the checker and the runtime module. Preserve all matching facts so the core, not the reader, decides uniqueness.

- [ ] **Step 4: Add the two checked-in compatibility profiles and APK inspector**

Populate `targets.json` from the spec. The 8.0.69 tablet rule uses `Lenovo TB-9707F`; the 8.0.79 tablet rule uses `inTabletEnv, no tablet condition matched, return false`; both login rules use `loginAsOtherDeviceBtn`. Keep the exact descriptors in the spec as assertions, not as a replacement for anchor matching.

- [ ] **Step 5: Run static checks against both saved official APKs**

Run:

```bash
./gradlew :compat-checker:run --args='check --targets compatibility/wechat/targets.json --apk work/apks/wechat-8.0.69.apk'
./gradlew :compat-checker:run --args='check --targets compatibility/wechat/targets.json --apk work/apks/wechat-8.0.79.apk'
```

Expected: each command reports the matching version, verified identity, and exactly one result for each hook. The resolved descriptors must match the spec table. A deliberately modified test profile or wrong APK must exit nonzero.

- [ ] **Step 6: Commit the reader and profiles**

```bash
git add compat-core compat-checker compatibility/wechat/targets.json
git commit -m "feat: verify WeChat compatibility profiles"
```

### Task 4: Install the minimal runtime hooks with all-or-none behavior

**Files:**
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/InstalledBuildIdentityReader.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/HookCall.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/TinkerClassLoaderBridge.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/LibXposedHookRegistrar.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/TargetMethodResolver.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/HookCallbacks.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/HookInstaller.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/RuntimeCompatibilityResolver.kt`
- Create: `app/src/main/kotlin/io/github/nku100/wechatpad/runtime/RuntimeResolutionCache.kt`
- Create: `app/src/test/kotlin/io/github/nku100/wechatpad/runtime/TargetMethodResolverTest.kt`
- Create: `app/src/test/kotlin/io/github/nku100/wechatpad/runtime/TinkerClassLoaderBridgeTest.kt`
- Create: `app/src/test/kotlin/io/github/nku100/wechatpad/runtime/HookCallbacksTest.kt`
- Create: `app/src/test/kotlin/io/github/nku100/wechatpad/runtime/HookInstallerTest.kt`
- Create: `app/src/test/kotlin/io/github/nku100/wechatpad/runtime/InstalledBuildIdentityReaderTest.kt`
- Create: `app/src/test/kotlin/io/github/nku100/wechatpad/runtime/RuntimeCompatibilityResolverTest.kt`
- Create: `app/src/test/kotlin/io/github/nku100/wechatpad/runtime/RuntimeResolutionCacheTest.kt`
- Modify: `compat-core/src/main/kotlin/io/github/nku100/wechatpad/compat/ResolutionCache.kt`
- Modify: `compat-core/src/test/kotlin/io/github/nku100/wechatpad/compat/ResolutionCacheTest.kt`
- Modify: `app/src/main/kotlin/io/github/nku100/wechatpad/WeChatPadModule.kt`
- Modify: `app/build.gradle.kts`

**Interfaces:**
- `InstalledBuild(identity: BuildIdentity, apkFiles: List<File>, installFingerprint: String, dataDirectory: File)` carries the observed package name and ABI, installed APK paths, private data directory, and a quick cache invalidation fingerprint.
- `InstalledBuildIdentityReader.read(applicationInfo: ApplicationInfo): InstalledBuild` reads package name, APK/split paths, ABI, UID, file size/mtime, and data directory without hashing APK contents.
- API 102's package-loaded callback runs before `Application` creation and only supplies `ApplicationInfo`, which has no version or signer data. On a cache miss, hash the installed base APK and match its exact hash to a registered profile; combine that profile's version and signer with the observed package name and ABI before calling the shared resolver. On a cache hit, validate the stored key against one registered profile and recheck package name, ABI, and install fingerprint before using the result.
- `TinkerClassLoaderBridge.install(classLoader: ClassLoader, onReady: (ClassLoader) -> Unit): HookRegistration` hooks `TinkerApplication.onBaseContextAttached(Context, long, long)` after the call and supplies the post-Tinker classloader.
- `TargetMethodResolver.resolve(classLoader: ClassLoader, descriptor: String): Method` converts the resolved DEX descriptor to a reflected method and rejects missing or signature-mismatched methods.
- `HookInstaller.install(tabletMethod: Method, loginMethod: Method): InstallOutcome` registers both API 102 hooks; if either registration fails, it removes any hook already installed and returns failure.
- Hook callbacks use the action ids already present in `HookRule`; tablet behavior matches the reference commit’s call-stack exception and login behavior only changes `GONE` to `VISIBLE`.
- The runtime reads `compatibility/wechat/targets.json` from the APK asset packaged from the root file; it does not maintain a second profile copy.

- [x] **Step 1: Write callback, method-descriptor, bootstrap, identity, cache, and install-rollback tests**

Cover object/primitive/array descriptor conversion, missing method rejection, Tinker post-attach classloader delivery, tablet result for chat/non-chat stacks, login visibility for `GONE`/`VISIBLE`/`INVISIBLE`, first-hook failure, second-hook failure with first-hook removal, and successful two-hook installation.

- [x] **Step 2: Run runtime unit tests to verify they fail**

Run: `./gradlew :app:testDebugUnitTest --tests '*TargetMethodResolverTest' --tests '*TinkerClassLoaderBridgeTest' --tests '*HookCallbacksTest' --tests '*HookInstallerTest'`
Expected: FAIL because runtime resolvers and installer are absent.

- [x] **Step 3: Implement package identity, shared DEX resolution, and cache loading**

On the `com.tencent.mm` main-process callback, reject other processes or a non-WeChat package; the `minApiVersion=102` metadata prevents frameworks without API 102 from loading this entry point. Read the same target JSON and use package name, ABI, APK file metadata, resolver version, and feature-rule version to locate a cache entry indexed by the install fingerprint. Validate the serialized resolution key against one registered profile before using it. On a miss, compute the installed base APK SHA-256, select the exact statically or locally runtime-verified profile by APK hash, run `DexFactReader`, and call the same `CompatibilityResolver` as the checker in `INSTALLED_PACKAGE` mode. Store successful results under WeChat’s private files using the registered APK SHA-256, signer, version code, resolver version, and feature-rule version. Recompute on APK identity or either rules version changing and treat invalid cache data as a miss.

- [x] **Step 4: Resolve both runtime methods before installing either hook**

After package-manager identity and shared DEX resolution succeed, install the temporary Tinker bootstrap hook. Once `onBaseContextAttached` returns, resolve both descriptors through Tinker’s actual classloader, then install the tablet and login hooks. Remove the temporary bootstrap hook on every exit path; roll back the tablet hook if login-hook registration fails. Unsupported builds never receive even the bootstrap hook. Log build identity, compatibility status, resolved descriptors, cache hit/miss, and failure reason without logging account data.

- [x] **Step 5: Implement the two callback behaviors and run unit tests**

For tablet detection, proceed through the original call, then return `false` when the stack contains `com.tencent.mm.pluginsdk.ui.chat`; otherwise return `true`. For the login visibility hook, inspect argument 0 and set its visibility to `VISIBLE` only when it is `GONE`. This preserves the behavior in [WeChatTablet commit 7f53c39](https://github.com/Xposed-Modules-Repo/top.hookvip.wxtablet/commit/7f53c39ca271454c699a39f48174231e5bde4b7e) and its [hook callback](https://github.com/Xposed-Modules-Repo/top.hookvip.wxtablet/blob/92cc10eab9cb56afcb3de884f6966a700aa6d159/app/src/main/java/top/hookvip/wxtablet/entry/TabletHooker.kt).

Run: `./gradlew :compat-core:test :compat-checker:test :app:testDebugUnitTest :app:assembleDebug verifyModuleMetadata`
Expected: PASS; the debug APK contains one profile resource, the API 102 entry, and no WeChatTablet/DexKit/YukiHookAPI artifacts.

- [x] **Step 6: Commit the runtime implementation**

```bash
git add app compat-core
git commit -m "feat: add WeChat tablet login hooks"
```

### Task 5: Run the isolated local AVD smoke matrix

**Files:**
- Modify: dedicated local AVD configuration only if required to use an installed Android 37.2 Google APIs ARM64 system image with 16 KB pages.
- Create: `docs/validation/wechatpad-local-smoke.md`
- Modify: `compatibility/wechat/targets.json` after each successful local runtime result.
- Modify: `docs/superpowers/specs/2026-10-04-wechatpad-design.md` to record the completed phase and any evidence-driven design correction.

**Interfaces:**
- Create or use a dedicated local Android 17 / API 37 ARM64 AVD with 16 KB pages and a root-capable setup for official LSPosed. Keep its name, serial, and host configuration path local; select the serial from the live device list for each command.
- Use an official LSPosed release that supports libxposed API 102 and record its version in the validation report.
- A successful smoke changes the target status from `static-verified` to `runtime-verified-local`; a failed smoke leaves it static-only and records the observed failure.

- [x] **Step 1: Configure the dedicated AVD and boot it visibly**

Use an installed Android 37.2 Google APIs ARM64 system image with 16 KB pages. Create a separate AVD for this validation, configure the required root-capable setup, and confirm it boots visibly as Android 17 / API 37. Do not change unrelated AVDs or issue commands to unrelated running emulators.

- [x] **Step 2: Verify official LSPosed and the no-module baseline**

Confirm the installed official LSPosed release is active and API 102 is available. Disable the WeChat scope for other WeChat modules and disable WeChatPad; launch each target build in the visible window and record the baseline login page and available login options.

- [x] **Step 3: Enable the module and smoke 8.0.69**

Enable `io.github.nku100.wechatpad` for `com.tencent.mm`, force-stop/relaunch WeChat, verify the LSPosed hook-install log, confirm the tablet login entry is visible, and open its QR login page. Do not scan the QR code or sign in.

- [x] **Step 4: Repeat baseline and hooked smoke for 8.0.79**

Replace the app with the saved 8.0.79 APK, confirm the baseline, then repeat the hooked login-entry and QR-page checks. Also update from 8.0.69 to 8.0.79 with WeChatPad enabled and verify cache invalidation followed by a cache hit on a subsequent cold start. Keep the emulator window visible throughout.

- [x] **Step 5: Record evidence and update statuses**

Record both WeChat version codes, AVD image, official LSPosed version/API, baseline/hooked results, and any failure logs in `docs/validation/wechatpad-local-smoke.md`. Mark a target `runtime-verified-local` only when both its baseline and hooked smoke pass.

- [x] **Step 6: Commit the local validation record**

```bash
git add compatibility/wechat/targets.json docs/validation/wechatpad-local-smoke.md docs/superpowers/specs/2026-10-04-wechatpad-design.md
git commit -m "test: record local WeChat login smoke results"
```

## Self-Review

- **Spec coverage:** Tasks 1–4 implement the modern module, shared core/DEX reader, strict build identity, dual-hook atomicity, diagnostics, and cache. Task 5 performs the required local two-version matrix. GitHub build CI and automatic compatibility PRs are intentionally outside this phase and remain the next agreed stages.
- **Step scan:** Each task has an independently checkable build, unit-test, static-APK, runtime-hook, or AVD result. No task asks the implementer to invent a feature rule or callback action.
- **Type consistency:** `BuildIdentity`, `DexMethodFact`, `HookRule`, `CompatibilityTarget`, `CompatibilityResolver`, and `ResolutionCacheKey` are defined in Task 2 and consumed with the same names in Tasks 3–4.
- **Review focus:** Identity rejection is tested in Task 2/3; anchor collision and signature mismatch in Task 2/3; multi-DEX traversal in Task 3; rollback in Task 4; cache key invalidation in Task 2 and update smoke in Task 5.
- **Proportion:** The plan is limited to the local adaptation milestone; it does not draft workflows or scheduled tasks for the later CI milestones.
