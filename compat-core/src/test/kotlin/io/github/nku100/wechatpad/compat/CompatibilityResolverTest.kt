package io.github.nku100.wechatpad.compat

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

class CompatibilityResolverTest {
    @Test
    fun resolvesBothHooksForAnExactRegisteredBuild() {
        val result = resolve()

        assertEquals(CompatibilityStatus.COMPATIBLE, result.status)
        assertEquals(
            mapOf(
                TABLET_RULE.id to TABLET_METHOD,
                LOGIN_RULE.id to LOGIN_METHOD,
            ),
            result.resolvedDescriptors,
        )
    }

    @Test
    fun rejectsAProfileWithNoHooks() {
        val result = resolve(target = target(hooks = emptyList()))

        assertRejected(result, CompatibilityStatus.INVALID_PROFILE)
    }

    @Test
    fun rejectsAProfileMissingTheTabletHook() {
        val result = resolve(target = target(hooks = listOf(LOGIN_RULE)))

        assertRejected(result, CompatibilityStatus.INVALID_PROFILE)
    }

    @Test
    fun rejectsAProfileMissingTheLoginHook() {
        val result = resolve(target = target(hooks = listOf(TABLET_RULE)))

        assertRejected(result, CompatibilityStatus.INVALID_PROFILE)
    }

    @Test
    fun rejectsAProfileWithDuplicateHookIds() {
        val result = resolve(target = target(hooks = listOf(TABLET_RULE, TABLET_RULE, LOGIN_RULE)))

        assertRejected(result, CompatibilityStatus.INVALID_PROFILE)
    }

    @Test
    fun rejectsMissingAnchorsWithoutKeepingPartialHooks() {
        val result = resolve(facts = validFacts().dropLast(1))

        assertRejected(result, CompatibilityStatus.MISSING_ANCHOR)
    }

    @Test
    fun rejectsMultipleMethodsWithTheSameAnchorAndShape() {
        val result = resolve(facts = validFacts() + validFacts().first())

        assertRejected(result, CompatibilityStatus.AMBIGUOUS_MATCH)
    }

    @Test
    fun rejectsAnAnchorWhoseMethodShapeDoesNotMatch() {
        val wrongShape = validFacts().first().copy(
            parameterDescriptors = listOf("Ljava/lang/Object;"),
        )
        val result = resolve(facts = listOf(wrongShape, validFacts().last()))

        assertRejected(result, CompatibilityStatus.SIGNATURE_MISMATCH)
    }

    @Test
    fun rejectsAnAnchorWhoseReturnTypeDoesNotMatch() {
        val wrongReturnType = validFacts().first().copy(returnDescriptor = "Ljava/lang/Object;")
        val result = resolve(facts = listOf(wrongReturnType, validFacts().last()))

        assertRejected(result, CompatibilityStatus.SIGNATURE_MISMATCH)
    }

    @Test
    fun rejectsTheRightVersionWithTheWrongPackage() {
        val result = resolve(identity = REGISTERED_IDENTITY.copy(packageName = "com.example.other"))

        assertRejected(result, CompatibilityStatus.IDENTITY_MISMATCH)
    }

    @Test
    fun rejectsAnUnregisteredVersionCode() {
        val result = resolve(identity = REGISTERED_IDENTITY.copy(versionCode = 3201))

        assertRejected(result, CompatibilityStatus.UNKNOWN_BUILD)
    }

    @Test
    fun rejectsTheRightBuildSignedByAnotherCertificate() {
        val result = resolve(identity = REGISTERED_IDENTITY.copy(signerSha256 = WRONG_SHA256))

        assertRejected(result, CompatibilityStatus.IDENTITY_MISMATCH)
    }

    @Test
    fun rejectsTheRightBuildWithAnotherApkHash() {
        val result = resolve(identity = REGISTERED_IDENTITY.copy(apkSha256 = WRONG_SHA256))

        assertRejected(result, CompatibilityStatus.IDENTITY_MISMATCH)
    }

    @Test
    fun requiresAnApkHashForStaticEvidence() {
        val result = resolve(identity = REGISTERED_IDENTITY.copy(apkSha256 = null))

        assertRejected(result, CompatibilityStatus.IDENTITY_MISMATCH)
    }

    @Test
    fun permitsPackageEvidenceToDeferHashingUntilACacheMiss() {
        val result = resolve(
            identity = REGISTERED_IDENTITY.copy(apkSha256 = null),
            verification = IdentityVerification.INSTALLED_PACKAGE,
        )

        assertEquals(CompatibilityStatus.COMPATIBLE, result.status)
    }

    @Test
    fun rejectsAnUnknownVersion() {
        val result = resolve(
            identity = REGISTERED_IDENTITY.copy(versionName = "9.0.0", versionCode = 9000),
        )

        assertRejected(result, CompatibilityStatus.UNKNOWN_BUILD)
    }

    @Test
    fun reportsAnUnregisteredBuildAfterItsTrustedIdentityMatches() {
        val identity = REGISTERED_IDENTITY.copy(versionName = "8.0.80", versionCode = 3220)
        val result = resolveCandidate(identity)

        assertEquals(CompatibilityStatus.UNKNOWN_BUILD, result.status)
        assertTrue(result.reason.contains("signer"))
    }

    @Test
    fun rejectsAnUnregisteredCandidateSignedByAnotherCertificate() {
        val identity = REGISTERED_IDENTITY.copy(
            versionName = "8.0.80",
            versionCode = 3220,
            signerSha256 = WRONG_SHA256,
        )

        assertRejected(resolveCandidate(identity), CompatibilityStatus.IDENTITY_MISMATCH)
    }

    @Test
    fun rejectsAnUnregisteredCandidateWithAnotherPackage() {
        val identity = REGISTERED_IDENTITY.copy(
            packageName = "com.example.other",
            versionName = "8.0.80",
            versionCode = 3220,
        )

        assertRejected(resolveCandidate(identity), CompatibilityStatus.IDENTITY_MISMATCH)
    }

    @Test
    fun rejectsAnUnregisteredCandidateWithAnotherAbi() {
        val identity = REGISTERED_IDENTITY.copy(
            abi = "armeabi-v7a",
            versionName = "8.0.80",
            versionCode = 3220,
        )

        assertRejected(resolveCandidate(identity), CompatibilityStatus.IDENTITY_MISMATCH)
    }

    @Test
    fun rejectsTheOldLenovoAnchorCollisionEvenWhenItsMethodShapeMatches() {
        val obsoleteRule = TABLET_RULE.copy(
            stringAnchor = "Lenovo TB-9707F",
            expectedDescriptor = TABLET_METHOD,
        )
        val target = target(hooks = listOf(obsoleteRule, LOGIN_RULE))
        val oldHelper = TABLET_FACT.copy(
            descriptor = "Lcom/tencent/mm/ui/other;->isLenovoTablet()Z",
            strings = setOf("Lenovo TB-9707F"),
        )
        val result = resolve(target = target, facts = listOf(oldHelper, LOGIN_FACT))

        assertRejected(result, CompatibilityStatus.DESCRIPTOR_MISMATCH)
    }

    @Test
    fun decodesTheCheckedInTargetFixture() {
        val fixture = File("src/test/resources/targets-test.json").readText()
        val targets = Json.decodeFromString<List<CompatibilityTarget>>(fixture)

        assertEquals(1, targets.size)
        assertEquals("8.0.69", targets.single().identity.versionName)
        assertEquals("https://dldir1v6.qq.com/weixin/android/weixin8069android3040_0x2800455a_arm64.apk", targets.single().sourceUrl)
        assertEquals(VerificationStatus.STATIC_VERIFIED, targets.single().verificationStatus)
        assertEquals(listOf("tablet", "login"), targets.single().hooks.map(HookRule::id))
    }

    private fun resolve(
        identity: BuildIdentity = REGISTERED_IDENTITY,
        verification: IdentityVerification = IdentityVerification.STATIC_APK,
        target: CompatibilityTarget = target(),
        facts: List<DexMethodFact> = validFacts(),
    ): CompatibilityResult = CompatibilityResolver.resolve(
        identity = identity,
        verification = verification,
        targets = listOf(target),
        facts = facts,
    )

    private fun resolveCandidate(
        identity: BuildIdentity,
        targets: List<CompatibilityTarget> = listOf(target()),
        facts: List<DexMethodFact> = validFacts(),
    ): CompatibilityResult = CompatibilityResolver.resolveStaticCandidate(
        identity = identity,
        targets = targets,
        facts = facts,
    )

    private fun target(
        identity: BuildIdentity = REGISTERED_IDENTITY,
        hooks: List<HookRule> = listOf(TABLET_RULE, LOGIN_RULE),
    ) = CompatibilityTarget(identity, featureRulesVersion = 1, hooks = hooks)

    private fun validFacts() = listOf(TABLET_FACT, LOGIN_FACT)

    private fun assertRejected(
        result: CompatibilityResult,
        expectedStatus: CompatibilityStatus,
    ) {
        assertEquals(expectedStatus, result.status, result.reason)
        assertTrue(result.resolvedDescriptors.isEmpty())
    }

    private companion object {
        const val TABLET_METHOD = "Lcom/tencent/mm/ui/ok;->C(Lpv5/w0;)Z"
        const val LOGIN_METHOD = "Lfb1/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V"
        const val WRONG_SHA256 = "0000000000000000000000000000000000000000000000000000000000000000"

        val REGISTERED_IDENTITY = BuildIdentity(
            packageName = "com.tencent.mm",
            versionName = "8.0.79",
            versionCode = 3200,
            abi = "arm64-v8a",
            apkSha256 = "5feb100337981467fd257c3ad66bb171f54a69d2579b2ecc70d5a628db8e7282",
            signerSha256 = "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c",
        )
        val TABLET_RULE = HookRule(
            id = "tablet",
            stringAnchor = "inTabletEnv, no tablet condition matched, return false",
            parameterDescriptors = listOf("Lpv5/w0;"),
            returnDescriptor = "Z",
            expectedDescriptor = TABLET_METHOD,
        )
        val LOGIN_RULE = HookRule(
            id = "login",
            stringAnchor = "loginAsOtherDeviceBtn",
            parameterDescriptors = listOf("Landroid/view/View;", "Landroidx/lifecycle/y;"),
            returnDescriptor = "V",
            expectedDescriptor = LOGIN_METHOD,
        )
        val TABLET_FACT = DexMethodFact(
            descriptor = TABLET_METHOD,
            parameterDescriptors = listOf("Lpv5/w0;"),
            returnDescriptor = "Z",
            strings = setOf("inTabletEnv, no tablet condition matched, return false"),
        )
        val LOGIN_FACT = DexMethodFact(
            descriptor = LOGIN_METHOD,
            parameterDescriptors = listOf("Landroid/view/View;", "Landroidx/lifecycle/y;"),
            returnDescriptor = "V",
            strings = setOf("loginAsOtherDeviceBtn"),
        )
    }
}
