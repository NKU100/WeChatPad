package io.github.nku100.impad.runtime

import android.content.Context
import com.tencent.tinker.loader.app.TinkerApplication
import java.lang.reflect.Method
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue

class TinkerClassLoaderBridgeTest {
    @Test
    fun suppliesTheClassLoaderAfterBaseContextAttachedReturns() {
        val postAttachLoader = javaClass.classLoader!!
        val application = TinkerApplication(postAttachLoader)
        var originalCalled = false
        var readyClassLoader: ClassLoader? = null
        var registeredMethod: Method? = null
        var registeredCallback: HookCallback? = null
        var unhooked = false
        val registrar = object : HookRegistrar {
            override fun hook(method: Method, id: String, callback: HookCallback): HookRegistration {
                assertEquals("onBaseContextAttached", method.name)
                registeredMethod = method
                registeredCallback = callback
                return HookRegistration { unhooked = true }
            }
        }

        TinkerClassLoaderBridge(
            registrar = registrar,
            postAttachClassLoader = { (it as TinkerApplication).postAttachClassLoader },
        ).install(javaClass.classLoader!!) { readyClassLoader = it }
        val result = registeredCallback!!.intercept(HookCall(application, emptyArray()) {
            originalCalled = true
            "original"
        })

        assertEquals("onBaseContextAttached", registeredMethod!!.name)
        assertTrue(originalCalled)
        assertTrue(unhooked)
        assertSame(postAttachLoader, readyClassLoader)
        assertEquals("original", result)
    }

    @Test
    fun removesBootstrapHookWhenPostAttachResolutionFails() {
        val application = TinkerApplication(javaClass.classLoader!!)
        var registeredCallback: HookCallback? = null
        var unhooked = false
        val registrar = object : HookRegistrar {
            override fun hook(method: Method, id: String, callback: HookCallback): HookRegistration {
                registeredCallback = callback
                return HookRegistration { unhooked = true }
            }
        }
        TinkerClassLoaderBridge(
            registrar = registrar,
            postAttachClassLoader = { (it as TinkerApplication).postAttachClassLoader },
        ).install(javaClass.classLoader!!) { error("resolution failure") }

        assertFailsWith<IllegalStateException> {
            registeredCallback!!.intercept(HookCall(application, emptyArray()) { "original" })
        }
        assertTrue(unhooked)
    }
}
