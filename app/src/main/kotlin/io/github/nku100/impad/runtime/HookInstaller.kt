package io.github.nku100.impad.runtime

import java.lang.reflect.Method

data class HookSpec(val method: Method, val id: String, val callback: HookCallback)

class HookInstaller(private val registrar: HookRegistrar) {
    fun install(hooks: List<HookSpec>): InstallOutcome {
        val registrations = mutableListOf<HookRegistration>()
        return try {
            require(hooks.isNotEmpty()) { "Hook list must not be empty" }
            require(hooks.all { it.id.isNotBlank() } && hooks.map { it.id }.distinct().size == hooks.size) {
                "Hook IDs must be non-empty and unique"
            }
            for (hook in hooks) {
                registrations += registrar.hook(hook.method, hook.id, hook.callback)
            }
            InstallOutcome.Installed(registrations.toList())
        } catch (error: Throwable) {
            for (registration in registrations.asReversed()) {
                try {
                    registration.unhook()
                } catch (rollbackError: Throwable) {
                    error.addSuppressed(rollbackError)
                }
            }
            if (error is VirtualMachineError || error is ThreadDeath) throw error
            InstallOutcome.Failed(error.message ?: error.javaClass.simpleName)
        }
    }
}

sealed interface InstallOutcome {
    data class Installed(val registrations: List<HookRegistration>) : InstallOutcome
    data class Failed(val reason: String) : InstallOutcome
}
