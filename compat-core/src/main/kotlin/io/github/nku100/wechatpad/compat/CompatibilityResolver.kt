package io.github.nku100.wechatpad.compat

object CompatibilityResolver {
    private val requiredHookIds = setOf("tablet", "login")

    fun resolve(
        identity: BuildIdentity,
        verification: IdentityVerification,
        targets: List<CompatibilityTarget>,
        facts: List<DexMethodFact>,
    ): CompatibilityResult {
        val target = targets.singleOrNull {
            it.identity.versionName == identity.versionName &&
                it.identity.versionCode == identity.versionCode
        } ?: return rejected(CompatibilityStatus.UNKNOWN_BUILD, "No target registered for this WeChat version")

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
        if (hookIds.size != requiredHookIds.size || hookIds.toSet() != requiredHookIds) {
            return rejected(
                CompatibilityStatus.INVALID_PROFILE,
                "Profile must define exactly one 'tablet' hook and one 'login' hook",
            )
        }

        val resolved = linkedMapOf<String, String>()
        for (rule in target.hooks) {
            val anchored = facts.filter { rule.stringAnchor in it.strings }
            if (anchored.isEmpty()) {
                return rejected(CompatibilityStatus.MISSING_ANCHOR, "Hook '${rule.id}' anchor was not found")
            }

            val matchingShape = anchored.filter {
                it.parameterDescriptors == rule.parameterDescriptors &&
                    it.returnDescriptor == rule.returnDescriptor
            }
            if (matchingShape.isEmpty()) {
                return rejected(CompatibilityStatus.SIGNATURE_MISMATCH, "Hook '${rule.id}' method shape changed")
            }
            if (matchingShape.size > 1) {
                return rejected(CompatibilityStatus.AMBIGUOUS_MATCH, "Hook '${rule.id}' matched multiple methods")
            }

            val method = matchingShape.single()
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
    ): CompatibilityResult {
        val matchingTargets = targets.filter {
            it.identity.versionName == identity.versionName &&
                it.identity.versionCode == identity.versionCode
        }
        if (matchingTargets.size > 1) {
            return rejected(CompatibilityStatus.INVALID_PROFILE, "Multiple profiles register this WeChat version")
        }
        if (matchingTargets.size == 1) {
            return resolve(identity, IdentityVerification.STATIC_APK, targets, facts)
        }

        val latestVersionCode = targets.maxOfOrNull { it.identity.versionCode }
            ?: return rejected(CompatibilityStatus.UNKNOWN_BUILD, "No compatibility targets are registered")
        val latestTargets = targets.filter { it.identity.versionCode == latestVersionCode }
        val trustedIdentity = latestTargets.singleOrNull()?.identity
            ?: return rejected(CompatibilityStatus.INVALID_PROFILE, "Newest compatibility target is ambiguous")
        if (!matchesTrustedIdentity(identity, trustedIdentity)) {
            return rejected(
                CompatibilityStatus.IDENTITY_MISMATCH,
                "Package, ABI, or signer does not match the newest registered WeChat build",
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
