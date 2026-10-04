package io.github.nku100.wechatpad.compat

import kotlinx.serialization.Serializable

@Serializable
data class HookRule(
    val id: String,
    val stringAnchor: String,
    val parameterDescriptors: List<String>,
    val returnDescriptor: String,
    val expectedDescriptor: String,
)

@Serializable
data class CompatibilityTarget(
    val identity: BuildIdentity,
    val featureRulesVersion: Int,
    val hooks: List<HookRule>,
)
