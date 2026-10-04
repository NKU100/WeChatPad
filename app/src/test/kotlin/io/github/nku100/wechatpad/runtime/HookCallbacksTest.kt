package io.github.nku100.wechatpad.runtime

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

class HookCallbacksTest {
    @Test
    fun tabletDetectionProceedsAndDisablesTabletModeOnlyForChatStack() {
        var originalCalls = 0
        val callbacks = HookCallbacks(
            stackTraceProvider = {
                arrayOf(StackTraceElement("com.tencent.mm.pluginsdk.ui.chat.ChatUI", "send", null, 1))
            },
        )

        val result = callbacks.tabletDetection(HookCall(null, emptyArray()) {
            originalCalls++
            true
        })

        assertEquals(false, result)
        assertEquals(1, originalCalls)
    }

    @Test
    fun tabletDetectionReturnsTrueForNonChatCallers() {
        val callbacks = HookCallbacks(
            stackTraceProvider = { arrayOf(StackTraceElement("com.tencent.mm.ui.HomeUI", "open", null, 1)) },
        )
        var originalCalls = 0

        val result = callbacks.tabletDetection(HookCall(null, emptyArray()) {
            originalCalls++
            false
        })

        assertEquals(true, result)
        assertEquals(1, originalCalls)
    }

    @Test
    fun loginEntryChangesOnlyGoneViewsAndPreservesTheOriginalResult() {
        val callbacks = HookCallbacks(
            isView = { it is TestView },
            visibilityOf = { (it as TestView).visibility },
            setVisibility = { view, visibility -> (view as TestView).visibility = visibility },
        )
        val cases = listOf(
            GONE to VISIBLE,
            VISIBLE to VISIBLE,
            INVISIBLE to INVISIBLE,
        )

        cases.forEach { (initial, expected) ->
            val view = TestView(initial)
            var originalCalls = 0
            val result = callbacks.loginEntry(HookCall(null, arrayOf(view)) {
                originalCalls++
                "original-result"
            })

            assertEquals(expected, view.visibility)
            assertEquals("original-result", result)
            assertEquals(1, originalCalls)
        }
    }

    private data class TestView(var visibility: Int)

    private companion object {
        const val VISIBLE = 0
        const val INVISIBLE = 4
        const val GONE = 8
    }
}
