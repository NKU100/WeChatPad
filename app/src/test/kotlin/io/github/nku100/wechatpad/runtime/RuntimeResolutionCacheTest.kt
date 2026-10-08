package io.github.nku100.wechatpad.runtime

import io.github.nku100.wechatpad.compat.CompatibilityResult
import io.github.nku100.wechatpad.compat.CompatibilityStatus
import io.github.nku100.wechatpad.compat.COMPATIBILITY_RESOLVER_VERSION
import io.github.nku100.wechatpad.compat.ResolutionCacheKey
import java.nio.file.Files
import java.util.Comparator
import kotlin.test.assertEquals
import kotlin.test.assertNull
import org.junit.jupiter.api.Test

class RuntimeResolutionCacheTest {
    @Test
    fun indexesTheSharedCacheByInstallationFingerprint() {
        withCache { cache ->
            val key = cacheKey()
            val result = CompatibilityResult(
                status = CompatibilityStatus.COMPATIBLE,
                reason = "all hooks resolved",
                resolvedDescriptors = mapOf("tablet" to "Lx/y;->tablet()Z"),
            )
            cache.write(INSTALL_FINGERPRINT, key, result)

            assertEquals(result, cache.read(INSTALL_FINGERPRINT)?.result)
            assertNull(cache.read(OTHER_FINGERPRINT))
        }
    }

    @Test
    fun preservesTheRegisteredProfileKeyForCallerValidation() {
        withCache { cache ->
            val key = cacheKey()
            val result = CompatibilityResult(
                status = CompatibilityStatus.COMPATIBLE,
                reason = "all hooks resolved",
                resolvedDescriptors = mapOf("tablet" to "Lx/y;->tablet()Z"),
            )
            cache.write(INSTALL_FINGERPRINT, key, result)

            assertEquals(key, cache.read(INSTALL_FINGERPRINT)?.key)
            assertEquals(1, cache.read(INSTALL_FINGERPRINT)?.key?.featureRulesVersion)
        }
    }

    private fun withCache(block: (RuntimeResolutionCache) -> Unit) {
        val directory = Files.createTempDirectory("wechatpad runtime cache")
        try {
            block(RuntimeResolutionCache(directory.toFile()))
        } finally {
            Files.walk(directory).use { paths ->
                paths.sorted(Comparator.reverseOrder<java.nio.file.Path>()).forEach(Files::deleteIfExists)
            }
        }
    }

    private fun cacheKey() = ResolutionCacheKey(
        apkSha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        signerSha256 = "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c",
        versionCode = 4000,
        resolverVersion = COMPATIBILITY_RESOLVER_VERSION,
        featureRulesVersion = 1,
    )

    private companion object {
        val INSTALL_FINGERPRINT = "a".repeat(64)
        val OTHER_FINGERPRINT = "b".repeat(64)
    }
}
