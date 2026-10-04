package io.github.nku100.wechatpad.runtime

import java.io.File
import io.github.nku100.wechatpad.compat.BuildIdentity
import io.github.nku100.wechatpad.compat.COMPATIBILITY_RESOLVER_VERSION
import io.github.nku100.wechatpad.compat.CompatibilityResolver
import io.github.nku100.wechatpad.compat.CompatibilityResult
import io.github.nku100.wechatpad.compat.CompatibilityStatus
import io.github.nku100.wechatpad.compat.CompatibilityTarget
import io.github.nku100.wechatpad.compat.DexFactReader
import io.github.nku100.wechatpad.compat.DexMethodFact
import io.github.nku100.wechatpad.compat.IdentityVerification
import io.github.nku100.wechatpad.compat.ResolutionCacheKey
import io.github.nku100.wechatpad.compat.VerificationStatus

data class RuntimeResolution(
    val target: CompatibilityTarget?,
    val result: CompatibilityResult,
    val cacheHit: Boolean,
)

class RuntimeCompatibilityResolver(
    targets: List<CompatibilityTarget>,
    private val cache: RuntimeResolutionCache,
    private val hashApk: (File) -> String = InstalledBuildIdentityReader()::sha256,
    private val readFacts: (List<File>, Set<String>) -> List<DexMethodFact> = DexFactReader::scan,
) {
    private val targets = targets.filter {
        it.verificationStatus == VerificationStatus.STATIC_VERIFIED ||
            it.verificationStatus == VerificationStatus.RUNTIME_VERIFIED_LOCAL
    }

    fun resolve(build: InstalledBuild): RuntimeResolution {
        val cached = try {
            cache.read(build.installFingerprint)
        } catch (_: Exception) {
            null
        }
        val cachedTarget = cached?.let { entry ->
            targets.singleOrNull { it.cacheKey() == entry.key }
        }
        if (cached != null && cachedTarget != null) {
            val identity = cachedTarget.identity.forInstalledBuild(build)
            if (!identity.matchesTargetIdentity(cachedTarget)) {
                val result = CompatibilityResolver.resolve(
                    identity = identity,
                    verification = IdentityVerification.INSTALLED_PACKAGE,
                    targets = targets,
                    facts = emptyList(),
                )
                return RuntimeResolution(cachedTarget, result, cacheHit = false)
            }

            val expectedDescriptors = cachedTarget.hooks.associate { it.id to it.expectedDescriptor }
            if (cached.result.resolvedDescriptors == expectedDescriptors) {
                return RuntimeResolution(cachedTarget, cached.result, cacheHit = true)
            }
        }

        val apkSha256 = hashApk(build.apkFiles.first())
        val target = targets.singleOrNull {
            it.identity.apkSha256.equals(apkSha256, ignoreCase = true)
        } ?: return RuntimeResolution(
            target = null,
            result = CompatibilityResult(
                status = CompatibilityStatus.UNKNOWN_BUILD,
                reason = "Installed APK SHA-256 is not registered",
            ),
            cacheHit = false,
        )

        val identity = target.identity.forInstalledBuild(build, apkSha256)
        if (!identity.matchesTargetIdentity(target)) {
            val result = CompatibilityResolver.resolve(
                identity = identity,
                verification = IdentityVerification.INSTALLED_PACKAGE,
                targets = targets,
                facts = emptyList(),
            )
            return RuntimeResolution(target, result, cacheHit = false)
        }

        val facts = readFacts(build.apkFiles, target.hooks.mapTo(linkedSetOf()) { it.stringAnchor })
        val result = CompatibilityResolver.resolve(
            identity = identity,
            verification = IdentityVerification.INSTALLED_PACKAGE,
            targets = targets,
            facts = facts,
        )
        if (result.status == CompatibilityStatus.COMPATIBLE) {
            try {
                cache.write(build.installFingerprint, target.cacheKey(), result)
            } catch (_: Exception) {
                // A cache write failure must not prevent compatible hooks from being installed.
            }
        }
        return RuntimeResolution(target, result, cacheHit = false)
    }

    private fun CompatibilityTarget.cacheKey() = ResolutionCacheKey(
        apkSha256 = checkNotNull(identity.apkSha256),
        signerSha256 = identity.signerSha256,
        versionCode = identity.versionCode,
        resolverVersion = COMPATIBILITY_RESOLVER_VERSION,
        featureRulesVersion = featureRulesVersion,
    )

    private fun BuildIdentity.forInstalledBuild(
        build: InstalledBuild,
        apkSha256: String? = this.apkSha256,
    ) = copy(
        packageName = build.identity.packageName,
        abi = build.identity.abi,
        apkSha256 = apkSha256,
    )

    private fun BuildIdentity.matchesTargetIdentity(target: CompatibilityTarget): Boolean =
        packageName == target.identity.packageName && abi == target.identity.abi
}
