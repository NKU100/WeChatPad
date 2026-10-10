package io.github.nku100.impad.apps.wechat

import io.github.nku100.impad.runtime.HookCallback
import io.github.nku100.impad.runtime.HookRegistrar
import io.github.nku100.impad.runtime.HookRegistration
import io.github.nku100.impad.runtime.InstallOutcome

import java.lang.reflect.Method
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class WeChatHookInstallerTest {
    @Test
    fun rollsBackTheTabletHookWhenLoginRegistrationFails() {
        val registrar = RecordingRegistrar(failOnCall = 2)

        val outcome = WeChatHookInstaller(registrar).install(tabletMethod(), loginMethod())

        assertIs<InstallOutcome.Failed>(outcome)
        assertEquals(listOf("wechatpad_tablet"), registrar.removedIds)
        assertEquals(listOf("wechatpad_tablet", "wechatpad_login"), registrar.attemptedIds)
    }

    @Test
    fun leavesNoHookWhenTheFirstRegistrationFails() {
        val registrar = RecordingRegistrar(failOnCall = 1)

        val outcome = WeChatHookInstaller(registrar).install(tabletMethod(), loginMethod())

        assertIs<InstallOutcome.Failed>(outcome)
        assertTrue(registrar.removedIds.isEmpty())
        assertEquals(listOf("wechatpad_tablet"), registrar.attemptedIds)
    }

    @Test
    fun reportsBothRegistrationsOnSuccess() {
        val registrar = RecordingRegistrar()

        val outcome = WeChatHookInstaller(registrar).install(tabletMethod(), loginMethod())

        assertIs<InstallOutcome.Installed>(outcome)
        assertEquals(listOf("wechatpad_tablet", "wechatpad_login"), registrar.attemptedIds)
        assertEquals(2, outcome.registrations.size)
    }

    private fun tabletMethod(): Method = javaClass.getDeclaredMethod("tabletHookTarget")

    private fun loginMethod(): Method = javaClass.getDeclaredMethod("loginHookTarget")

    private fun tabletHookTarget(): Boolean = false

    private fun loginHookTarget(): Unit = Unit

    private class RecordingRegistrar(private val failOnCall: Int? = null) : HookRegistrar {
        val attemptedIds = mutableListOf<String>()
        val removedIds = mutableListOf<String>()

        override fun hook(method: Method, id: String, callback: HookCallback): HookRegistration {
            attemptedIds += id
            if (attemptedIds.size == failOnCall) error("injected registration failure")
            return HookRegistration { removedIds += id }
        }
    }
}
