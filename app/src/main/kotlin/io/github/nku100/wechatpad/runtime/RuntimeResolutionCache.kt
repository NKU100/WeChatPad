package io.github.nku100.wechatpad.runtime

import io.github.nku100.wechatpad.compat.CompatibilityResult
import io.github.nku100.wechatpad.compat.ResolutionCache
import io.github.nku100.wechatpad.compat.ResolutionCacheEntry
import io.github.nku100.wechatpad.compat.ResolutionCacheKey
import java.io.File

class RuntimeResolutionCache(private val directory: File) {
    fun read(installFingerprint: String): ResolutionCacheEntry? =
        cacheFor(installFingerprint).readAnyCompatible()

    fun write(installFingerprint: String, key: ResolutionCacheKey, result: CompatibilityResult) {
        cacheFor(installFingerprint).write(key, result)
    }

    private fun cacheFor(installFingerprint: String): ResolutionCache {
        require(installFingerprint.matches(FINGERPRINT_PATTERN)) { "Invalid installation fingerprint" }
        return ResolutionCache(File(directory, "resolution-$installFingerprint.json"))
    }

    private companion object {
        val FINGERPRINT_PATTERN = Regex("[a-fA-F0-9]{64}")
    }
}
