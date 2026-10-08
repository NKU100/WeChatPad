package io.github.nku100.wechatpad.compat

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

class CandidateCompatibilityAnalyzerTest {
    @Test
    fun hostedRuntimeVerificationRemainsUsableAsABaseline() {
        val baseline = forwardSafeSameShapeBaseline().copy(verificationStatus = VerificationStatus.RUNTIME_VERIFIED_HOSTED)
        val report = analyze(baseline = baseline)
        assertEquals(CandidatePipelineStatus.STATIC_VERIFIED_PENDING_RUNTIME, report.status)
    }

    @Test
    fun generatesAStaticProfileWhenEveryForwardSafeHookMatchesUniquely() {
        val report = analyze(baseline = forwardSafeSameShapeBaseline())

        assertEquals(CandidatePipelineStatus.STATIC_VERIFIED_PENDING_RUNTIME, report.status)
        assertEquals(listOf("8.0.69", "8.0.78", "8.0.79"), report.checkedVersions)
        assertEquals(CandidateHookStatus.UNIQUE_MATCH, report.hooks.first { it.hookId == "tablet" }.status)
        assertEquals(CandidateHookStatus.UNIQUE_MATCH, report.hooks.first { it.hookId == "login" }.status)
        assertEquals(TABLET_79, report.suggestedProfile?.hooks?.first { it.id == "tablet" }?.expectedDescriptor)
        assertEquals(VerificationStatus.STATIC_VERIFIED, report.suggestedProfile?.verificationStatus)
    }

    @Test
    fun requestsReviewWhenTheReal78TabletHookShapeChangesIn79() {
        val report = analyze()

        assertEquals(CandidatePipelineStatus.NEEDS_HOOK_REVIEW, report.status)
        assertEquals(CandidateHookStatus.SIGNATURE_MISMATCH, report.hooks.first { it.hookId == "tablet" }.status)
        assertEquals(TABLET_79, report.hooks.first { it.hookId == "tablet" }.candidateDescriptors.single())
    }

    @Test
    fun refusesForwardInferenceFromAnUnsafeAnchorEvenWhenItMatchesUniquely() {
        val baseline = baseline69().copy(hooks = baseline69().hooks.map {
            if (it.id == "login") it.copy(safeForForwardInference = true) else it
        })
        val facts = candidateFacts() + DexMethodFact(
            descriptor = "Lcom/tencent/mm/ui/other;->isLenovoTablet()Z",
            parameterDescriptors = listOf("Lfd5/n0;"),
            returnDescriptor = "Z",
            strings = setOf("Lenovo TB-9707F"),
        )

        val report = analyze(baseline = baseline, facts = facts)

        assertEquals(CandidatePipelineStatus.NEEDS_HOOK_REVIEW, report.status)
        assertEquals(CandidateHookStatus.UNSAFE_ANCHOR, report.hooks.first { it.hookId == "tablet" }.status)
        assertNull(report.suggestedProfile)
    }

    @Test
    fun reportsMissingAnchorSeparately() {
        val report = analyze(facts = candidateFacts().filterNot { TABLET_ANCHOR_78 in it.strings })

        assertEquals(CandidatePipelineStatus.NEEDS_HOOK_REVIEW, report.status)
        assertEquals(CandidateHookStatus.MISSING_ANCHOR, report.hooks.first { it.hookId == "tablet" }.status)
    }

    @Test
    fun reportsChangedMethodShapeSeparately() {
        val wrongShape = TABLET_FACT.copy(parameterDescriptors = listOf("Ljava/lang/Object;"))

        val report = analyze(facts = listOf(wrongShape, LOGIN_FACT))

        assertEquals(CandidateHookStatus.SIGNATURE_MISMATCH, report.hooks.first { it.hookId == "tablet" }.status)
    }

    @Test
    fun reportsAmbiguousAnchorMatchesSeparately() {
        val secondMatch = TABLET_FACT_78.copy(descriptor = "Lcom/tencent/mm/ui/other;->tabletAgain(Lou5/w0;)Z")

        val report = analyze(facts = listOf(TABLET_FACT_78, secondMatch, LOGIN_FACT))

        assertEquals(CandidateHookStatus.AMBIGUOUS_MATCH, report.hooks.first { it.hookId == "tablet" }.status)
        assertNull(report.suggestedProfile)
    }

    @Test
    fun rejectsAnInvalidBaselineBeforeMatchingCandidateFacts() {
        val invalidBaseline = baseline78().copy(hooks = listOf(TABLET_RULE_78, TABLET_RULE_78))

        val report = analyze(baseline = invalidBaseline)

        assertEquals(CandidatePipelineStatus.BASELINE_INVALID, report.status)
        assertEquals("8.0.78", report.baselineVersion)
        assertNull(report.suggestedProfile)
    }

    @Test
    fun rejectsABaselineOutsideTheSelectedRegressionWindow() {
        val report = analyze(
            baseline = forwardSafeSameShapeBaseline(),
            checkedVersions = listOf("8.0.69", "8.0.79"),
        )

        assertEquals(CandidatePipelineStatus.BASELINE_INVALID, report.status)
        assertEquals(listOf("Adaptation baseline is not included in the static regression window"), report.blockers)
    }

    @Test
    fun rejectsCandidateIdentityBeforeInspectingHooks() {
        val report = analyze(identity = CANDIDATE_IDENTITY.copy(signerSha256 = "0".repeat(64)))

        assertEquals(CandidatePipelineStatus.IDENTITY_REJECTED, report.status)
        assertEquals(emptyList(), report.hooks)
        assertNull(report.suggestedProfile)
    }

    @Test
    fun leavesAResolvedCandidateUnverifiedWhenRegressionFails() {
        val report = analyze(baseline = forwardSafeSameShapeBaseline(), regressionPassed = false)

        assertEquals(CandidatePipelineStatus.STATIC_REGRESSION_FAILED, report.status)
        assertNull(report.suggestedProfile)
        assertEquals(listOf("8.0.69", "8.0.78", "8.0.79"), report.checkedVersions)
    }

    @Test
    fun rejectsIllegalStatusTransitions() {
        assertFailsWith<IllegalStateException> {
            CandidatePipelineStateMachine.transition(
                CandidatePipelineStatus.DISCOVERED,
                CandidatePipelineEvent.STATIC_REGRESSION_PASSED,
            )
        }
    }

    @Test
    fun recordsFetchAndRuntimeFailuresAsTerminalStates() {
        assertEquals(
            CandidatePipelineStatus.FETCH_FAILED,
            CandidatePipelineStateMachine.transition(
                CandidatePipelineStatus.DISCOVERED,
                CandidatePipelineEvent.DOWNLOAD_FAILED,
            ),
        )
        assertEquals(
            CandidatePipelineStatus.RUNTIME_REJECTED,
            CandidatePipelineStateMachine.transition(
                CandidatePipelineStatus.WAITING_RUNTIME,
                CandidatePipelineEvent.RUNTIME_FAILED,
            ),
        )
    }

    @Test
    fun formalSupportRequiresTheLocalRuntimeResultAndMergedPullRequest() {
        var status = CandidatePipelineStatus.DISCOVERED
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.APK_FETCHED)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.IDENTITY_ACCEPTED)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.BASELINE_ACCEPTED)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.STATIC_REGRESSION_PASSED)
        assertEquals(CandidatePipelineStatus.STATIC_VERIFIED_PENDING_RUNTIME, status)

        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.DRAFT_PR_CREATED)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.RUNTIME_PASSED)
        assertEquals(CandidatePipelineStatus.RUNTIME_VERIFIED, status)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.PULL_REQUEST_MERGED)

        assertEquals(CandidatePipelineStatus.FORMALLY_SUPPORTED, status)
    }

    @Test
    fun reportsARegisteredLocallyVerifiedCandidateAsFormalOnlyWhenItIsOnMain() {
        val report = CandidateCompatibilityAnalyzer.analyzeRegistered(
            identity = CANDIDATE_IDENTITY,
            target = registered79(),
            facts = candidateFacts(),
            checkedVersions = listOf("8.0.69", "8.0.78", "8.0.79"),
            regressionPassed = true,
            profileMergedToMain = true,
        )

        assertEquals(CandidatePipelineStatus.FORMALLY_SUPPORTED, report.status)
    }

    @Test
    fun reusesRegisteredRuntimeVerificationWithoutInventingAPullRequest() {
        var status = CandidatePipelineStatus.DISCOVERED
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.APK_FETCHED)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.IDENTITY_ACCEPTED)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.BASELINE_ACCEPTED)
        status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.STATIC_REGRESSION_PASSED)
        status = CandidatePipelineStateMachine.transition(
            status,
            CandidatePipelineEvent.REGISTERED_RUNTIME_VERIFICATION_CONFIRMED,
        )

        assertEquals(CandidatePipelineStatus.RUNTIME_VERIFIED, status)
    }

    @Test
    fun keepsARegisteredLocallyVerifiedCandidateShortOfFormalSupportUntilItIsOnMain() {
        val report = CandidateCompatibilityAnalyzer.analyzeRegistered(
            identity = CANDIDATE_IDENTITY,
            target = registered79(),
            facts = candidateFacts(),
            checkedVersions = listOf("8.0.69", "8.0.78", "8.0.79"),
            regressionPassed = true,
            profileMergedToMain = false,
        )

        assertEquals(CandidatePipelineStatus.RUNTIME_VERIFIED, report.status)
    }

    private fun analyze(
        identity: BuildIdentity = CANDIDATE_IDENTITY,
        baseline: CompatibilityTarget = baseline78(),
        facts: List<DexMethodFact> = candidateFacts(),
        regressionPassed: Boolean = true,
        checkedVersions: List<String> = listOf("8.0.69", "8.0.78", "8.0.79"),
    ) = CandidateCompatibilityAnalyzer.analyze(
        identity = identity,
        baseline = baseline,
        facts = facts,
        checkedVersions = checkedVersions,
        regressionPassed = regressionPassed,
    )

    private fun baseline69() = CompatibilityTarget(
        identity = BuildIdentity(
            packageName = "com.tencent.mm",
            versionName = "8.0.69",
            versionCode = 3040,
            abi = "arm64-v8a",
            apkSha256 = null,
            signerSha256 = SIGNER_SHA256,
        ),
        featureRulesVersion = 1,
        hooks = listOf(
            HookRule("tablet", "Lenovo TB-9707F", listOf("Lfd5/n0;"), "Z", "Lcom/tencent/mm/ui/qj;->B(Lfd5/n0;)Z"),
            HookRule("login", "loginAsOtherDeviceBtn", listOf("Landroid/view/View;", "Landroidx/lifecycle/y;"), "V", "Lg21/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V"),
        ),
        verificationStatus = VerificationStatus.RUNTIME_VERIFIED_LOCAL,
    )

    private fun baseline78() = CompatibilityTarget(
        identity = baseline69().identity.copy(versionName = "8.0.78", versionCode = 3180),
        featureRulesVersion = 1,
        hooks = listOf(TABLET_RULE_78, LOGIN_RULE_78),
        verificationStatus = VerificationStatus.RUNTIME_VERIFIED_LOCAL,
    )

    private fun forwardSafeSameShapeBaseline() = baseline78().copy(
        hooks = listOf(
            TABLET_RULE_78.copy(
                parameterDescriptors = listOf("Lpv5/w0;"),
                expectedDescriptor = "Lcom/tencent/mm/ui/gk;->C(Lpv5/w0;)Z",
            ),
            LOGIN_RULE_78,
        ),
    )

    private fun registered79() = baseline78().copy(
        identity = CANDIDATE_IDENTITY,
        hooks = listOf(
            TABLET_RULE_78.copy(
                parameterDescriptors = listOf("Lpv5/w0;"),
                expectedDescriptor = TABLET_79,
            ),
            LOGIN_RULE_78.copy(expectedDescriptor = "Lfb1/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V"),
        ),
        verificationStatus = VerificationStatus.RUNTIME_VERIFIED_LOCAL,
    )

    private fun candidateFacts() = listOf(TABLET_FACT, LOGIN_FACT)

    private companion object {
        const val SIGNER_SHA256 = "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c"
        const val TABLET_ANCHOR_78 = "inTabletEnv, no tablet condition matched, return false"
        const val TABLET_79 = "Lcom/tencent/mm/ui/ok;->C(Lpv5/w0;)Z"

        val CANDIDATE_IDENTITY = BuildIdentity(
            packageName = "com.tencent.mm",
            versionName = "8.0.79",
            versionCode = 3200,
            abi = "arm64-v8a",
            apkSha256 = "5feb100337981467fd257c3ad66bb171f54a69d2579b2ecc70d5a628db8e7282",
            signerSha256 = SIGNER_SHA256,
        )
        val TABLET_RULE_78 = HookRule(
            "tablet",
            TABLET_ANCHOR_78,
            listOf("Lou5/w0;"),
            "Z",
            "Lcom/tencent/mm/ui/gk;->C(Lou5/w0;)Z",
            safeForForwardInference = true,
        )
        val LOGIN_RULE_78 = HookRule(
            "login",
            "loginAsOtherDeviceBtn",
            listOf("Landroid/view/View;", "Landroidx/lifecycle/y;"),
            "V",
            "Lva1/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V",
            safeForForwardInference = true,
        )
        val TABLET_FACT = DexMethodFact(
            TABLET_79,
            listOf("Lpv5/w0;"),
            "Z",
            setOf(TABLET_ANCHOR_78),
        )
        val TABLET_FACT_78 = DexMethodFact(
            "Lcom/tencent/mm/ui/gk;->C(Lou5/w0;)Z",
            listOf("Lou5/w0;"),
            "Z",
            setOf(TABLET_ANCHOR_78),
        )
        val LOGIN_FACT = DexMethodFact(
            "Lfb1/h0;->a(Landroid/view/View;Landroidx/lifecycle/y;)V",
            listOf("Landroid/view/View;", "Landroidx/lifecycle/y;"),
            "V",
            setOf("loginAsOtherDeviceBtn"),
        )
    }
}
