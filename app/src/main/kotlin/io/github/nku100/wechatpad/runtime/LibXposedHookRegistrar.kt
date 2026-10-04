package io.github.nku100.wechatpad.runtime

import io.github.libxposed.api.XposedInterface
import java.lang.reflect.Method

class LibXposedHookRegistrar(private val xposed: XposedInterface) : HookRegistrar {
    override fun hook(method: Method, id: String, callback: HookCallback): HookRegistration {
        val handle = xposed.hook(method)
            .setId(id)
            .setExceptionMode(XposedInterface.ExceptionMode.PROTECTIVE)
            .intercept { chain ->
                callback.intercept(
                    HookCall(chain.thisObject, chain.args.toTypedArray()) { chain.proceed() },
                )
            }
        return HookRegistration { handle.unhook() }
    }
}
