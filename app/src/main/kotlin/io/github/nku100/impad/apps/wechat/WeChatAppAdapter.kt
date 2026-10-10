package io.github.nku100.impad.apps.wechat

import android.util.Log
import io.github.nku100.impad.compat.apps.wechat.WeChatCompatibilityPolicy
import io.github.nku100.impad.runtime.AppAdapter
import io.github.nku100.impad.runtime.HookRegistrar
import io.github.nku100.impad.runtime.InstallOutcome
import io.github.nku100.impad.runtime.ModuleLog
import io.github.nku100.impad.runtime.TargetMethodResolver
import io.github.nku100.impad.runtime.TinkerClassLoaderBridge

class WeChatAppAdapter : AppAdapter {
    override val compatibilityPolicy = WeChatCompatibilityPolicy.policy

    override fun acceptsProcess(processName: String?): Boolean = processName == packageName

    override fun install(
        classLoader: ClassLoader,
        descriptors: Map<String, String>,
        registrar: HookRegistrar,
        log: ModuleLog,
    ) {
        val tabletDescriptor = checkNotNull(descriptors["tablet"]) {
            "Compatible result did not include the tablet descriptor"
        }
        val loginDescriptor = checkNotNull(descriptors["login"]) {
            "Compatible result did not include the login descriptor"
        }
        TinkerClassLoaderBridge(registrar).install(classLoader) { tinkerClassLoader ->
            try {
                val tabletMethod = TargetMethodResolver.resolve(tinkerClassLoader, tabletDescriptor)
                val loginMethod = TargetMethodResolver.resolve(tinkerClassLoader, loginDescriptor)
                log.write(Log.INFO, "resolved tablet=$tabletDescriptor login=$loginDescriptor", null)
                when (val outcome = WeChatHookInstaller(registrar).install(tabletMethod, loginMethod)) {
                    is InstallOutcome.Installed ->
                        log.write(Log.INFO, "installed ${outcome.registrations.size} WeChat hooks", null)
                    is InstallOutcome.Failed ->
                        log.write(Log.ERROR, "hook installation failed: ${outcome.reason}", null)
                }
            } catch (error: Throwable) {
                if (error is VirtualMachineError || error is ThreadDeath) throw error
                log.write(Log.ERROR, "post-Tinker method resolution failed: ${error.message ?: error.javaClass.simpleName}", error)
            }
        }
        log.write(Log.INFO, "waiting for Tinker class loader", null)
    }
}
