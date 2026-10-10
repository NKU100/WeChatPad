package io.github.nku100.impad.compat

import kotlinx.serialization.Serializable

@Serializable
data class BuildIdentity(
    val packageName: String,
    val versionName: String,
    val versionCode: Long,
    val abi: String,
    val apkSha256: String?,
    val signerSha256: String,
)

@Serializable
enum class IdentityVerification {
    STATIC_APK,
    INSTALLED_PACKAGE,
}
