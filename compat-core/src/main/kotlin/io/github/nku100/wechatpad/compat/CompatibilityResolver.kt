package io.github.nku100.wechatpad.compat

object CompatibilityResolver {
    fun resolve(
        identity: BuildIdentity,
        verification: IdentityVerification,
        targets: List<CompatibilityTarget>,
        facts: List<DexMethodFact>,
        requiredHookIds: Set<String>,
    ): CompatibilityResult {
        val sameBuild = targets.filter {
            it.identity.versionName == identity.versionName && it.identity.versionCode == identity.versionCode
        }
        val matchingBuild = sameBuild.filter {
            it.identity.packageName == identity.packageName && it.identity.abi == identity.abi
        }
        if (matchingBuild.size > 1) {
            return rejected(CompatibilityStatus.INVALID_PROFILE, "Multiple profiles register this app build")
        }
        val target = matchingBuild.singleOrNull()
            ?: return if (sameBuild.isEmpty()) {
                rejected(CompatibilityStatus.UNKNOWN_BUILD, "No target registered for this app build")
            } else {
                rejected(CompatibilityStatus.IDENTITY_MISMATCH, "Package or ABI does not match the target")
            }

        val expectedIdentity = target.identity
        if (!matchesTrustedIdentity(identity, expectedIdentity)) {
            return rejected(CompatibilityStatus.IDENTITY_MISMATCH, "Package, ABI, or signer does not match the target")
        }

        val expectedApkSha256 = expectedIdentity.apkSha256
        when (verification) {
            IdentityVerification.STATIC_APK -> {
                if (identity.apkSha256 == null || expectedApkSha256 == null ||
                    !identity.apkSha256.equals(expectedApkSha256, ignoreCase = true)
                ) {
                    return rejected(CompatibilityStatus.IDENTITY_MISMATCH, "APK SHA-256 does not match the target")
                }
            }

            IdentityVerification.INSTALLED_PACKAGE -> {
                if (identity.apkSha256 != null &&
                    (expectedApkSha256 == null || !identity.apkSha256.equals(expectedApkSha256, ignoreCase = true))
                ) {
                    return rejected(CompatibilityStatus.IDENTITY_MISMATCH, "APK SHA-256 does not match the target")
                }
            }
        }

        val hookIds = target.hooks.map(HookRule::id)
        if (requiredHookIds.isEmpty() || hookIds.size != requiredHookIds.size || hookIds.toSet() != requiredHookIds ||
            hookIds.any(String::isBlank) || hookIds.size != hookIds.toSet().size
        ) {
            return rejected(
                CompatibilityStatus.INVALID_PROFILE,
                "Profile must define unique, non-empty hook identifiers",
            )
        }

        val resolved = linkedMapOf<String, String>()
        for (rule in target.hooks) {
            val match = HookMethodMatcher.match(rule, facts)
            when (match.status) {
                HookMethodMatchStatus.MISSING_ANCHOR ->
                    return rejected(CompatibilityStatus.MISSING_ANCHOR, "Hook '${rule.id}' anchor was not found")
                HookMethodMatchStatus.SIGNATURE_MISMATCH ->
                    return rejected(CompatibilityStatus.SIGNATURE_MISMATCH, "Hook '${rule.id}' method shape changed")
                HookMethodMatchStatus.AMBIGUOUS_MATCH ->
                    return rejected(CompatibilityStatus.AMBIGUOUS_MATCH, "Hook '${rule.id}' matched multiple methods")
                HookMethodMatchStatus.UNIQUE_MATCH -> Unit
            }

            val method = match.shapeMatchedMethods.single()
            if (method.descriptor != rule.expectedDescriptor) {
                return rejected(CompatibilityStatus.DESCRIPTOR_MISMATCH, "Hook '${rule.id}' descriptor changed")
            }
            resolved[rule.id] = method.descriptor
        }

        return CompatibilityResult(
            status = CompatibilityStatus.COMPATIBLE,
            reason = "All ${target.hooks.size} hook methods resolved uniquely",
            resolvedDescriptors = resolved,
        )
    }

    fun resolveStaticCandidate(
        identity: BuildIdentity,
        targets: List<CompatibilityTarget>,
        facts: List<DexMethodFact>,
        requiredHookIds: Set<String>,
    ): CompatibilityResult {
        val matchingTargets = targets.filter {
            it.identity.versionName == identity.versionName &&
                it.identity.versionCode == identity.versionCode &&
                it.identity.packageName == identity.packageName &&
                it.identity.abi == identity.abi
        }
        if (matchingTargets.size > 1) {
            return rejected(CompatibilityStatus.INVALID_PROFILE, "Multiple profiles register this app build")
        }
        if (matchingTargets.size == 1) {
            return resolve(identity, IdentityVerification.STATIC_APK, targets, facts, requiredHookIds)
        }

        val appTargets = targets.filter {
            it.identity.packageName == identity.packageName && it.identity.abi == identity.abi &&
                it.identity.signerSha256.equals(identity.signerSha256, ignoreCase = true)
        }
        val latestVersionCode = appTargets.maxOfOrNull { it.identity.versionCode }
            ?: return rejected(CompatibilityStatus.IDENTITY_MISMATCH, "No compatibility target matches this app package and ABI")
        val latestTargets = appTargets.filter { it.identity.versionCode == latestVersionCode }
        val trustedIdentity = latestTargets.singleOrNull()?.identity
            ?: return rejected(CompatibilityStatus.INVALID_PROFILE, "Newest compatibility target is ambiguous")
        if (!matchesTrustedIdentity(identity, trustedIdentity)) {
            return rejected(
                CompatibilityStatus.IDENTITY_MISMATCH,
                "Package, ABI, or signer does not match the newest registered app build",
            )
        }

        return rejected(
            CompatibilityStatus.UNKNOWN_BUILD,
            "No target is registered for this version; package, ABI, and signer match the newest registered build",
        )
    }

    private fun matchesTrustedIdentity(identity: BuildIdentity, trustedIdentity: BuildIdentity): Boolean =
        identity.packageName == trustedIdentity.packageName &&
            identity.abi == trustedIdentity.abi &&
            identity.signerSha256.equals(trustedIdentity.signerSha256, ignoreCase = true)

    private fun rejected(status: CompatibilityStatus, reason: String) =
        CompatibilityResult(status = status, reason = reason)
}
