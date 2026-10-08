package io.github.nku100.wechatpad.runtime

import io.github.nku100.wechatpad.compat.BuildIdentity
import io.github.nku100.wechatpad.compat.COMPATIBILITY_RESOLVER_VERSION
import io.github.nku100.wechatpad.compat.CompatibilityStatus
import io.github.nku100.wechatpad.compat.CompatibilityTarget
import io.github.nku100.wechatpad.compat.DexMethodFact
import io.github.nku100.wechatpad.compat.HookRule
import io.github.nku100.wechatpad.compat.ResolutionCacheKey
import io.github.nku100.wechatpad.compat.VerificationStatus
import java.nio.file.Files
import java.util.Comparator
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.junit.jupiter.api.Test

class RuntimeCompatibilityResolverTest {
    @Test
    fun resolvesAndCachesAnExactProfileThenReusesItWithoutHashing() = withFixture { directory, apk ->
        var hashCalls = 0
        var scanCalls = 0
        val resolver = RuntimeCompatibilityResolver(
            targets = listOf(target()),
            cache = RuntimeResolutionCache(directory.resolve("cache").toFile()),
            hashApk = {
                hashCalls++
                APK_SHA256
            },
            readFacts = { _, _ ->
                scanCalls++
                facts()
            },
        )

        val first = resolver.resolve(installedBuild(directory, apk))
        val second = resolver.resolve(installedBuild(directory, apk))

        assertEquals(CompatibilityStatus.COMPATIBLE, first.result.status)
        assertFalse(first.cacheHit)
        assertEquals(CompatibilityStatus.COMPATIBLE, second.result.status)
        assertTrue(second.cacheHit)
        assertEquals(1, hashCalls)
        assertEquals(1, scanCalls)
    }

    @Test
    fun returnsUnknownBuildWithoutCachingWhenTheInstalledHashIsUnregistered() = withFixture { directory, apk ->
        val resolver = RuntimeCompatibilityResolver(
            targets = listOf(target()),
            cache = RuntimeResolutionCache(directory.resolve("cache").toFile()),
            hashApk = { UNKNOWN_SHA256 },
            readFacts = { _, _ -> error("DEX must not be scanned for an unknown build") },
        )

        val result = resolver.resolve(installedBuild(directory, apk))

        assertEquals(CompatibilityStatus.UNKNOWN_BUILD, result.result.status)
        assertFalse(result.cacheHit)
        assertEquals(null, result.target)
    }

    @Test
    fun doesNotTrustCachedDescriptorsThatDifferFromTheRegisteredProfile() = withFixture { directory, apk ->
        val cache = RuntimeResolutionCache(directory.resolve("cache").toFile())
        cache.write(
            "a".repeat(64),
            cacheKey(),
            io.github.nku100.wechatpad.compat.CompatibilityResult(
                status = CompatibilityStatus.COMPATIBLE,
                reason = "stale entry",
                resolvedDescriptors = mapOf("tablet" to "Lold/target;->a()Z"),
            ),
        )
        var hashCalls = 0
        var scanCalls = 0
        val resolver = RuntimeCompatibilityResolver(
            targets = listOf(target()),
            cache = cache,
            hashApk = {
                hashCalls++
                APK_SHA256
            },
            readFacts = { _, _ ->
                scanCalls++
                facts()
            },
        )

        val result = resolver.resolve(installedBuild(directory, apk))

        assertEquals(CompatibilityStatus.COMPATIBLE, result.result.status)
        assertFalse(result.cacheHit)
        assertEquals(1, hashCalls)
        assertEquals(1, scanCalls)
    }

    @Test
    fun recomputesCacheEntriesFromThePreviousResolverVersion() = withFixture { directory, apk ->
        val cache = RuntimeResolutionCache(directory.resolve("cache").toFile())
        cache.write(
            "a".repeat(64),
            cacheKey().copy(resolverVersion = 1),
            io.github.nku100.wechatpad.compat.CompatibilityResult(
                status = CompatibilityStatus.COMPATIBLE,
                reason = "previous resolver version",
                resolvedDescriptors = mapOf(
                    "tablet" to TABLET_METHOD,
                    "login" to LOGIN_METHOD,
                ),
            ),
        )
        var hashCalls = 0
        var scanCalls = 0
        val resolver = RuntimeCompatibilityResolver(
            targets = listOf(target()),
            cache = cache,
            hashApk = {
                hashCalls++
                APK_SHA256
            },
            readFacts = { _, _ ->
                scanCalls++
                facts()
            },
        )

        val result = resolver.resolve(installedBuild(directory, apk))

        assertEquals(CompatibilityStatus.COMPATIBLE, result.result.status)
        assertFalse(result.cacheHit)
        assertEquals(1, hashCalls)
        assertEquals(1, scanCalls)
    }

    @Test
    fun doesNotUseProfilesWithoutStaticOrRuntimeVerification() = withFixture { directory, apk ->
        val resolver = RuntimeCompatibilityResolver(
            targets = listOf(target().copy(verificationStatus = VerificationStatus.UNVERIFIED)),
            cache = RuntimeResolutionCache(directory.resolve("cache").toFile()),
            hashApk = { APK_SHA256 },
            readFacts = { _, _ -> error("Unverified profiles must not be scanned") },
        )

        val result = resolver.resolve(installedBuild(directory, apk))

        assertEquals(CompatibilityStatus.UNKNOWN_BUILD, result.result.status)
        assertEquals(null, result.target)
    }

    private fun installedBuild(directory: java.nio.file.Path, apk: java.io.File) = InstalledBuild(
        identity = BuildIdentity(
            packageName = "com.tencent.mm",
            versionName = "",
            versionCode = 0,
            abi = "arm64-v8a",
            apkSha256 = null,
            signerSha256 = "",
        ),
        apkFiles = listOf(apk),
        installFingerprint = "a".repeat(64),
        dataDirectory = directory.toFile(),
    )

    private fun facts() = listOf(
        DexMethodFact(TABLET_METHOD, listOf("Lfixture/NewEnvironment;"), "Z", setOf(TABLET_ANCHOR)),
        DexMethodFact(LOGIN_METHOD, listOf("Landroid/view/View;", "Landroidx/lifecycle/y;"), "V", setOf(LOGIN_ANCHOR)),
    )

    private fun target() = CompatibilityTarget(
        identity = BuildIdentity(
            packageName = "com.tencent.mm",
            versionName = "8.0.90",
            versionCode = 4000,
            abi = "arm64-v8a",
            apkSha256 = APK_SHA256,
            signerSha256 = SIGNER_SHA256,
        ),
        featureRulesVersion = 1,
        verificationStatus = VerificationStatus.STATIC_VERIFIED,
        hooks = listOf(
            HookRule("tablet", TABLET_ANCHOR, listOf("Lfixture/NewEnvironment;"), "Z", TABLET_METHOD),
            HookRule("login", LOGIN_ANCHOR, listOf("Landroid/view/View;", "Landroidx/lifecycle/y;"), "V", LOGIN_METHOD),
        ),
    )

    private fun withFixture(block: (java.nio.file.Path, java.io.File) -> Unit) {
        val directory = Files.createTempDirectory("wechatpad runtime resolver")
        try {
            val apk = directory.resolve("base.apk").toFile()
            Files.write(apk.toPath(), byteArrayOf(1, 2, 3))
            block(directory, apk)
        } finally {
            Files.walk(directory).use { paths ->
                paths.sorted(Comparator.reverseOrder<java.nio.file.Path>()).forEach(Files::deleteIfExists)
            }
        }
    }

    private companion object {
        fun cacheKey() = ResolutionCacheKey(
            apkSha256 = APK_SHA256,
            signerSha256 = SIGNER_SHA256,
            versionCode = 4000,
            resolverVersion = COMPATIBILITY_RESOLVER_VERSION,
            featureRulesVersion = 1,
        )

        const val APK_SHA256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        const val UNKNOWN_SHA256 = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        const val SIGNER_SHA256 = "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c"
        const val TABLET_ANCHOR = "tablet-anchor"
        const val LOGIN_ANCHOR = "login-anchor"
        const val TABLET_METHOD = "Lfixture/NewTablet;->C(Lfixture/NewEnvironment;)Z"
        const val LOGIN_METHOD = "Lfixture/NewLogin;->a(Landroid/view/View;Landroidx/lifecycle/y;)V"
    }
}
