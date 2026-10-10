package io.github.nku100.impad.compat

enum class HookMethodMatchStatus {
    MISSING_ANCHOR,
    SIGNATURE_MISMATCH,
    AMBIGUOUS_MATCH,
    UNIQUE_MATCH,
}

data class HookMethodMatch(
    val status: HookMethodMatchStatus,
    val anchoredMethods: List<DexMethodFact>,
    val shapeMatchedMethods: List<DexMethodFact>,
)

object HookMethodMatcher {
    fun match(rule: HookRule, facts: List<DexMethodFact>): HookMethodMatch {
        val anchoredMethods = facts.filter { rule.stringAnchor in it.strings }
        if (anchoredMethods.isEmpty()) {
            return HookMethodMatch(HookMethodMatchStatus.MISSING_ANCHOR, anchoredMethods, emptyList())
        }

        val shapeMatchedMethods = anchoredMethods.filter {
            it.parameterDescriptors == rule.parameterDescriptors && it.returnDescriptor == rule.returnDescriptor
        }
        val status = when {
            shapeMatchedMethods.isEmpty() -> HookMethodMatchStatus.SIGNATURE_MISMATCH
            shapeMatchedMethods.size > 1 -> HookMethodMatchStatus.AMBIGUOUS_MATCH
            else -> HookMethodMatchStatus.UNIQUE_MATCH
        }
        return HookMethodMatch(status, anchoredMethods, shapeMatchedMethods)
    }
}
