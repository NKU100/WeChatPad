package io.github.nku100.wechatpad.runtime

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertSame

class AppAdapterRegistryTest {
    @Test
    fun routesOnlyTheRegisteredPackageAndAcceptedProcess() {
        val adapter = FakeAdapter("example.app")
        val registry = AppAdapterRegistry(listOf(adapter))
        assertSame(adapter, registry.find("example.app", "example.app"))
        assertNull(registry.find("example.app", "example.app:push"))
        assertNull(registry.find("example.app", null))
        assertNull(registry.find("another.app", "another.app"))
    }

    @Test
    fun rejectsMultipleAdaptersForTheSamePackage() {
        assertFailsWith<IllegalArgumentException> {
            AppAdapterRegistry(listOf(FakeAdapter("example.app"), FakeAdapter("example.app")))
        }
    }

    @Test
    fun weChatAdapterKeepsMainProcessRestrictionAndUsesItsOwnRules() {
        val adapter = io.github.nku100.wechatpad.apps.wechat.WeChatAppAdapter()
        val registry = AppAdapterRegistry(listOf(adapter))
        assertSame(adapter, registry.find("com.tencent.mm", "com.tencent.mm"))
        assertNull(registry.find("com.tencent.mm", "com.tencent.mm:push"))
        assertNull(registry.find("com.tencent.mobileqq", "com.tencent.mobileqq:MSF"))
        assertEquals("assets/compatibility/wechat/targets.json", adapter.targetsAssetPath)
    }

    private class FakeAdapter(override val packageName: String) : AppAdapter {
        override val compatibilityPolicy = io.github.nku100.wechatpad.compat.apps.wechat.WeChatCompatibilityPolicy.policy
        override val targetsAssetPath = "assets/test/targets.json"
        override fun acceptsProcess(processName: String?): Boolean = processName == packageName
        override fun install(
            classLoader: ClassLoader,
            descriptors: Map<String, String>,
            registrar: HookRegistrar,
            log: ModuleLog,
        ) = Unit
    }
}
