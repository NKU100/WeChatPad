package io.github.nku100.wechatpad.compat

import kotlinx.serialization.Serializable

@Serializable
enum class CompatibilityStatus {
    COMPATIBLE,
    UNKNOWN_BUILD,
    IDENTITY_MISMATCH,
    MISSING_ANCHOR,
    SIGNATURE_MISMATCH,
    AMBIGUOUS_MATCH,
    DESCRIPTOR_MISMATCH,
}

@Serializable
data class CompatibilityResult(
    val status: CompatibilityStatus,
    val reason: String,
    val resolvedDescriptors: Map<String, String> = emptyMap(),
)
