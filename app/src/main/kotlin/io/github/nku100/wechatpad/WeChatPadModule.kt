package io.github.nku100.wechatpad

import android.content.pm.ApplicationInfo
import android.util.Log
import io.github.libxposed.api.XposedModule
import io.github.libxposed.api.XposedModuleInterface.ModuleLoadedParam
import io.github.libxposed.api.XposedModuleInterface.PackageLoadedParam
import io.github.nku100.wechatpad.compat.CompatibilityStatus
import io.github.nku100.wechatpad.compat.CompatibilityTarget
import io.github.nku100.wechatpad.runtime.HookInstaller
import io.github.nku100.wechatpad.runtime.InstalledBuildIdentityReader
import io.github.nku100.wechatpad.runtime.InstallOutcome
import io.github.nku100.wechatpad.runtime.LibXposedHookRegistrar
import io.github.nku100.wechatpad.runtime.RuntimeCompatibilityResolver
import io.github.nku100.wechatpad.runtime.RuntimeResolutionCache
import io.github.nku100.wechatpad.runtime.TargetMethodResolver
import io.github.nku100.wechatpad.runtime.TinkerClassLoaderBridge
import java.io.File
import java.nio.charset.StandardCharsets
import java.util.zip.ZipFile
import kotlinx.serialization.json.Json

class WeChatPadModule : XposedModule() {
    private var currentProcessName: String? = null
    private var packageHandled = false

    override fun onModuleLoaded(param: ModuleLoadedParam) {
        super.onModuleLoaded(param)
        currentProcessName = param.processName
    }

    override fun onPackageLoaded(param: PackageLoadedParam) {
        super.onPackageLoaded(param)
        if (packageHandled || param.packageName != WECHAT_PACKAGE) return

        val processName = currentProcessName
        if (processName != WECHAT_PACKAGE) {
            log(Log.INFO, "$WECHAT_PACKAGE process skipped: ${processName ?: "unknown"}")
            return
        }
        packageHandled = true

        try {
            initializeForWeChat(param.applicationInfo, param.defaultClassLoader)
        } catch (error: Throwable) {
            logFailure("module initialization failed", error)
        }
    }

    private fun initializeForWeChat(applicationInfo: ApplicationInfo, defaultClassLoader: ClassLoader) {
        val build = InstalledBuildIdentityReader().read(applicationInfo)
        val targets = readTargets()
        val cacheDirectory = File(build.dataDirectory, "files/wechatpad/compatibility")
        val resolution = RuntimeCompatibilityResolver(
            targets = targets,
            cache = RuntimeResolutionCache(cacheDirectory),
        ).resolve(build)

        val target = resolution.target
        val profileVersion = target?.identity?.versionName ?: "unknown"
        log(
            Log.INFO,
            "build=$profileVersion package=${build.identity.packageName} abi=${build.identity.abi} " +
                "apkSha256=${target?.identity?.apkSha256 ?: "unknown"} " +
                "signerSha256=${target?.identity?.signerSha256 ?: "unknown"} " +
                "status=${resolution.result.status} cacheHit=${resolution.cacheHit} reason=${resolution.result.reason}",
        )
        if (resolution.result.status != CompatibilityStatus.COMPATIBLE || target == null) return

        val tabletDescriptor = checkNotNull(resolution.result.resolvedDescriptors["tablet"]) {
            "Compatible result did not include the tablet descriptor"
        }
        val loginDescriptor = checkNotNull(resolution.result.resolvedDescriptors["login"]) {
            "Compatible result did not include the login descriptor"
        }
        val registrar = LibXposedHookRegistrar(this)
        val bridge = TinkerClassLoaderBridge(registrar)
        bridge.install(defaultClassLoader) { tinkerClassLoader ->
            try {
                val tabletMethod = TargetMethodResolver.resolve(tinkerClassLoader, tabletDescriptor)
                val loginMethod = TargetMethodResolver.resolve(tinkerClassLoader, loginDescriptor)
                log(Log.INFO, "resolved tablet=$tabletDescriptor login=$loginDescriptor")
                when (val outcome = HookInstaller(registrar).install(tabletMethod, loginMethod)) {
                    is InstallOutcome.Installed ->
                        log(Log.INFO, "installed ${outcome.registrations.size} WeChat hooks")

                    is InstallOutcome.Failed ->
                        log(Log.ERROR, "hook installation failed: ${outcome.reason}")
                }
            } catch (error: Throwable) {
                logFailure("post-Tinker method resolution failed", error)
            }
        }
        log(Log.INFO, "waiting for Tinker class loader")
    }

    private fun readTargets(): List<CompatibilityTarget> {
        val moduleApk = checkNotNull(getModuleApplicationInfo().sourceDir) {
            "Module APK path was null"
        }
        return ZipFile(moduleApk).use { apk ->
            val profile = checkNotNull(apk.getEntry(TARGETS_ASSET_PATH)) {
                "Compatibility profiles were missing from the module APK"
            }
            val json = apk.getInputStream(profile).bufferedReader(StandardCharsets.UTF_8).use { it.readText() }
            Json.decodeFromString<List<CompatibilityTarget>>(json)
        }
    }

    private fun log(priority: Int, message: String) {
        log(priority, LOG_TAG, message)
    }

    private fun logFailure(stage: String, error: Throwable) {
        if (error is VirtualMachineError || error is ThreadDeath) throw error
        log(Log.ERROR, LOG_TAG, "$stage: ${error.message ?: error.javaClass.simpleName}", error)
    }

    private companion object {
        const val WECHAT_PACKAGE = "com.tencent.mm"
        const val TARGETS_ASSET_PATH = "assets/compatibility/targets.json"
        const val LOG_TAG = "WeChatPad"
    }
}
