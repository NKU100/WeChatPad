package io.github.nku100.wechatpad.runtime

import java.lang.reflect.Method
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class BatchHookInstallerTest {
    @Test
    fun installsAnApplicationDefinedNumberOfHooks() {
        val registrar = RecordingRegistrar()
        val result = HookInstaller(registrar).install(specs("first", "second", "third"))
        assertIs<InstallOutcome.Installed>(result)
        assertEquals(3, result.registrations.size)
        assertEquals(listOf("first", "second", "third"), registrar.attempted)
    }

    @Test
    fun rollsBackEveryRegistrationInReverseOrderEvenIfUnhookFails() {
        val registrar = RecordingRegistrar(failRegistration = "third", failRollback = "second")
        val result = HookInstaller(registrar).install(specs("first", "second", "third"))
        assertIs<InstallOutcome.Failed>(result)
        assertEquals(listOf("second", "first"), registrar.removed)
    }

    @Test
    fun rejectsDuplicateHookIdsBeforeInstallingAnything() {
        val registrar = RecordingRegistrar()
        val result = HookInstaller(registrar).install(specs("same", "same"))
        assertIs<InstallOutcome.Failed>(result)
        assertTrue(registrar.attempted.isEmpty())
    }

    private fun specs(vararg ids: String): List<HookSpec> = ids.map { id ->
        HookSpec(javaClass.getDeclaredMethod("target"), id, HookCallback { it.proceed() })
    }

    private fun target(): Boolean = false

    private class RecordingRegistrar(
        private val failRegistration: String? = null,
        private val failRollback: String? = null,
    ) : HookRegistrar {
        val attempted = mutableListOf<String>()
        val removed = mutableListOf<String>()
        override fun hook(method: Method, id: String, callback: HookCallback): HookRegistration {
            attempted += id
            if (id == failRegistration) error("registration failed")
            return HookRegistration {
                removed += id
                if (id == failRollback) error("rollback failed")
            }
        }
    }
}
