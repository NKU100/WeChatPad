package io.github.nku100.impad.checker

import io.github.nku100.impad.compat.BuildIdentity
import io.github.nku100.impad.compat.CompatibilityTarget
import io.github.nku100.impad.compat.HookRule
import io.github.nku100.impad.compat.VerificationStatus
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CandidateBaselineSelectionTest {
    @Test
    fun prefersRuntimeVerifiedSameVersionAndRequiresDigestWhenAmbiguous() {
        val earlier = target(3180, "a".repeat(64))
        val sameVersionA = target(3200, "b".repeat(64))
        val sameVersionB = target(3200, "c".repeat(64))
        val candidate = identity(3200, "d".repeat(64))

        assertFailsWith<IllegalArgumentException> {
            selectCandidateBaseline(listOf(earlier, sameVersionA, sameVersionB), candidate)
        }
        assertEquals(
            sameVersionB,
            selectCandidateBaseline(listOf(earlier, sameVersionA, sameVersionB), candidate, "C".repeat(64)),
        )
    }

    @Test
    fun fallsBackToLatestEarlierRuntimeVerifiedVersion() {
        val older = target(3180, "a".repeat(64))
        val newest = target(3190, "b".repeat(64))
        assertEquals(newest, selectCandidateBaseline(listOf(older, newest), identity(3200, "c".repeat(64)))
        )
    }

    private fun target(versionCode: Long, digest: String) = CompatibilityTarget(
        identity = identity(versionCode, digest),
        featureRulesVersion = 1,
        hooks = listOf(
            HookRule("tablet", "tablet", emptyList(), "Z", "Lfixture/Tablet;->check()Z"),
            HookRule("login", "login", emptyList(), "V", "Lfixture/Login;->open()V"),
        ),
        verificationStatus = VerificationStatus.RUNTIME_VERIFIED_LOCAL,
    )

    private fun identity(versionCode: Long, digest: String) = BuildIdentity(
        packageName = "com.tencent.mm",
        versionName = if (versionCode == 3200L) "8.0.79" else "8.0.78",
        versionCode = versionCode,
        abi = "arm64-v8a",
        apkSha256 = digest,
        signerSha256 = "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c",
    )
}
