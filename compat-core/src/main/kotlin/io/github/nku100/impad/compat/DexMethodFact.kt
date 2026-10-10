package io.github.nku100.impad.compat

data class DexMethodFact(
    val descriptor: String,
    val parameterDescriptors: List<String>,
    val returnDescriptor: String,
    val strings: Set<String>,
)
