package io.github.nku100.impad.runtime

interface AppAdapter {
    val compatibilityPolicy: io.github.nku100.impad.compat.AppCompatibilityPolicy
    val packageName: String get() = compatibilityPolicy.packageName
    val targetsAssetPath: String get() = "assets/${compatibilityPolicy.targetsPath}"
    fun acceptsProcess(processName: String?): Boolean
    fun install(
        classLoader: ClassLoader,
        descriptors: Map<String, String>,
        registrar: HookRegistrar,
        log: ModuleLog,
    )
}

fun interface ModuleLog {
    fun write(priority: Int, message: String, error: Throwable?)
}
