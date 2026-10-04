package com.tencent.tinker.loader.app

import android.content.Context

class TinkerApplication(val postAttachClassLoader: ClassLoader) {
    @Suppress("UNUSED_PARAMETER")
    fun onBaseContextAttached(context: Context, startElapsedTime: Long, startTotalTime: Long) = Unit
}
