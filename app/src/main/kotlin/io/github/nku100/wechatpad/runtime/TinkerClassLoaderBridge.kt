package io.github.nku100.wechatpad.runtime

import android.content.Context
import java.lang.reflect.Method

class TinkerClassLoaderBridge(
    private val registrar: HookRegistrar,
    private val postAttachClassLoader: (Any) -> ClassLoader = { (it as Context).classLoader },
) {
    fun install(classLoader: ClassLoader, onReady: (ClassLoader) -> Unit): HookRegistration {
        val applicationClass = classLoader.loadClass(TINKER_APPLICATION_CLASS)
        val method = applicationClass.getDeclaredMethod(
            BASE_CONTEXT_ATTACHED_METHOD,
            Context::class.java,
            Long::class.javaPrimitiveType,
            Long::class.javaPrimitiveType,
        )
        var registration: HookRegistration? = null
        registration = registrar.hook(method, BOOTSTRAP_HOOK_ID) { call ->
            try {
                val result = call.proceed()
                val application = checkNotNull(call.thisObject) { "TinkerApplication receiver was null" }
                onReady(postAttachClassLoader(application))
                result
            } finally {
                registration?.unhook()
            }
        }
        return registration
    }

    private companion object {
        const val TINKER_APPLICATION_CLASS = "com.tencent.tinker.loader.app.TinkerApplication"
        const val BASE_CONTEXT_ATTACHED_METHOD = "onBaseContextAttached"
        const val BOOTSTRAP_HOOK_ID = "wechatpad_tinker_bootstrap"
    }
}
