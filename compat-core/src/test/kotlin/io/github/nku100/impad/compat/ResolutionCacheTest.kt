package io.github.nku100.impad.compat

import java.nio.file.Files
import java.util.Comparator
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ResolutionCacheTest {
    @Test
    fun returnsAStoredCompatibleResultForTheSameKey() = withCache { cache, key, _ ->
        val result = compatibleResult()

        cache.write(key, result)

        assertEquals(result, cache.read(key)?.result)
    }

    @Test
    fun returnsACompatibleEntryForRuntimeFingerprintLookup() = withCache { cache, key, _ ->
        val result = compatibleResult()
        cache.write(key, result)

        assertEquals(ResolutionCacheEntry(key, result), cache.readAnyCompatible())
    }

    @Test
    fun missesWhenAnyBuildOrRuleIdentityChanges() = withCache { cache, key, _ ->
        cache.write(key, compatibleResult())

        val changedKeys = listOf(
            key.copy(apkSha256 = DIFFERENT_SHA256),
            key.copy(signerSha256 = DIFFERENT_SHA256),
            key.copy(versionCode = key.versionCode + 1),
            key.copy(resolverVersion = key.resolverVersion + 1),
            key.copy(featureRulesVersion = key.featureRulesVersion + 1),
        )
        changedKeys.forEach { changedKey ->
            assertNull(cache.read(changedKey), "Expected cache miss for $changedKey")
        }
    }

    @Test
    fun treatsTruncatedOrInvalidJsonAsACacheMiss() = withCache { cache, key, file ->
        Files.writeString(file, "{\"key\":")
        assertNull(cache.read(key))

        Files.writeString(file, "not-json")
        assertNull(cache.read(key))
    }

    @Test
    fun doesNotReturnAnEntryWrittenForAnotherKey() = withCache { cache, key, file ->
        cache.write(key.copy(versionCode = key.versionCode - 1), compatibleResult())

        assertNull(cache.read(key))
        assertEquals(true, Files.size(file) > 0)
    }

    private fun compatibleResult() = CompatibilityResult(
        status = CompatibilityStatus.COMPATIBLE,
        reason = "both hooks resolved",
        resolvedDescriptors = mapOf("tablet" to "Lx/y;->tablet()Z", "login" to "Lx/y;->login()V"),
    )

    private inline fun withCache(block: (ResolutionCache, ResolutionCacheKey, java.nio.file.Path) -> Unit) {
        val directory = Files.createTempDirectory("impad-resolution-cache")
        try {
            val file = directory.resolve("resolution.json")
            block(
                ResolutionCache(file.toFile()),
                ResolutionCacheKey(
                    apkSha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    signerSha256 = "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c",
                    versionCode = 4000,
                    resolverVersion = COMPATIBILITY_RESOLVER_VERSION,
                    featureRulesVersion = 1,
                ),
                file,
            )
        } finally {
            Files.walk(directory).use { paths ->
                paths.sorted(Comparator.reverseOrder<java.nio.file.Path>()).forEach(Files::deleteIfExists)
            }
        }
    }

    private companion object {
        const val DIFFERENT_SHA256 = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    }
}
