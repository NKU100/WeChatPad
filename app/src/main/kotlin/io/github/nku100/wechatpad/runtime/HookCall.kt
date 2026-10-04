package io.github.nku100.wechatpad.runtime

class HookCall(
    val thisObject: Any?,
    val arguments: Array<Any?>,
    private val invokeOriginal: () -> Any?,
) {
    fun proceed(): Any? = invokeOriginal()
}

fun interface HookCallback {
    fun intercept(call: HookCall): Any?
}

fun interface HookRegistration {
    fun unhook()
}

fun interface HookRegistrar {
    fun hook(method: java.lang.reflect.Method, id: String, callback: HookCallback): HookRegistration
}
