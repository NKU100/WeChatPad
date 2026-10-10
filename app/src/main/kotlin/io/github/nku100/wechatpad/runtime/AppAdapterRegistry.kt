package io.github.nku100.wechatpad.runtime

class AppAdapterRegistry(adapters: List<AppAdapter>) {
    private val byPackage = adapters.associateBy(AppAdapter::packageName)

    init {
        require(byPackage.size == adapters.size) { "Each package must have exactly one app adapter" }
    }

    fun forPackage(packageName: String): AppAdapter? = byPackage[packageName]

    fun find(packageName: String, processName: String?): AppAdapter? =
        forPackage(packageName)?.takeIf { it.acceptsProcess(processName) }
}
