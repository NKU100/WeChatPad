package io.github.nku100.impad.apps.wechat

import android.view.View
import io.github.nku100.impad.runtime.HookCall

class WeChatHookCallbacks(
    private val stackTraceProvider: () -> Array<StackTraceElement> = { Thread.currentThread().stackTrace },
    private val isView: (Any) -> Boolean = { it is View },
    private val visibilityOf: (Any) -> Int = { (it as View).visibility },
    private val setVisibility: (Any, Int) -> Unit = { view, visibility -> (view as View).visibility = visibility },
) {
    fun tabletDetection(call: HookCall): Any? {
        call.proceed()
        val calledFromChat = stackTraceProvider().any { CHAT_PACKAGE in it.className }
        return !calledFromChat
    }

    fun loginEntry(call: HookCall): Any? {
        val originalResult = call.proceed()
        val view = call.arguments.firstOrNull()?.takeIf(isView) ?: return originalResult
        if (visibilityOf(view) == View.GONE) {
            setVisibility(view, View.VISIBLE)
        }
        return originalResult
    }

    private companion object {
        const val CHAT_PACKAGE = "com.tencent.mm.pluginsdk.ui.chat"
    }
}
