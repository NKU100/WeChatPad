package io.github.nku100.wechatpad.runtime

import java.lang.reflect.Method

class HookInstaller(
    private val registrar: HookRegistrar,
    private val callbacks: HookCallbacks = HookCallbacks(),
) {
    fun install(tabletMethod: Method, loginMethod: Method): InstallOutcome {
        var tabletRegistration: HookRegistration? = null
        return try {
            tabletRegistration = registrar.hook(tabletMethod, TABLET_HOOK_ID) { call ->
                callbacks.tabletDetection(call)
            }
            val loginRegistration = registrar.hook(loginMethod, LOGIN_HOOK_ID) { call ->
                callbacks.loginEntry(call)
            }
            InstallOutcome.Installed(listOf(tabletRegistration, loginRegistration))
        } catch (error: Throwable) {
            try {
                tabletRegistration?.unhook()
            } catch (rollbackError: Throwable) {
                error.addSuppressed(rollbackError)
            }
            if (error is VirtualMachineError || error is ThreadDeath) throw error
            InstallOutcome.Failed(error.message ?: error.javaClass.simpleName)
        }
    }

    private companion object {
        const val TABLET_HOOK_ID = "wechatpad_tablet"
        const val LOGIN_HOOK_ID = "wechatpad_login"
    }
}

sealed interface InstallOutcome {
    data class Installed(val registrations: List<HookRegistration>) : InstallOutcome
    data class Failed(val reason: String) : InstallOutcome
}
