package io.github.nku100.wechatpad.checker

import io.github.nku100.wechatpad.compat.CompatibilityResolver
import io.github.nku100.wechatpad.compat.CompatibilityStatus
import io.github.nku100.wechatpad.compat.CompatibilityTarget
import io.github.nku100.wechatpad.compat.CandidateCompatibilityAnalyzer
import io.github.nku100.wechatpad.compat.CandidateCompatibilityReport
import io.github.nku100.wechatpad.compat.CandidatePipelineEvent
import io.github.nku100.wechatpad.compat.CandidatePipelineStateMachine
import io.github.nku100.wechatpad.compat.CandidatePipelineStatus
import io.github.nku100.wechatpad.compat.AppCompatibilityPolicies
import io.github.nku100.wechatpad.compat.DexFactReader
import io.github.nku100.wechatpad.compat.VerificationStatus
import java.io.File
import java.io.FileWriter
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import kotlin.system.exitProcess

fun main(args: Array<String>) {
    try {
        when (args.firstOrNull()) {
            "check" -> checkCompatibility(parseArguments(args))
            "analyze-candidate" -> analyzeCandidate(parseCandidateArguments(args))
            else -> error("Usage: check ... | analyze-candidate ...")
        }
    } catch (error: Exception) {
        System.err.println("Compatibility check failed: ${error.message}")
        exitProcess(1)
    }
}

private fun checkCompatibility(arguments: CheckArguments) {
    val policy = AppCompatibilityPolicies.require(arguments.appId)
    require(arguments.targets.isFile) { "Target file does not exist: ${arguments.targets.absolutePath}" }
    val targets = Json.decodeFromString<List<CompatibilityTarget>>(arguments.targets.readText())
    policy.validateTargets(targets)

    val identity = ApkIdentityInspector().inspect(arguments.apk)
    policy.validateIdentity(identity)
    val anchors = targets.flatMap { target -> target.hooks.map { it.stringAnchor } }.toSet()
    val facts = DexFactReader.scan(listOf(arguments.apk), anchors)
    val result = CompatibilityResolver.resolveStaticCandidate(
        identity = identity,
        targets = targets,
        facts = facts,
        requiredHookIds = policy.requiredHookIds,
    )

    println("APK: ${arguments.apk.absolutePath}")
    println("Package: ${identity.packageName}")
    println("Version: ${identity.versionName} (${identity.versionCode})")
    println("ABI: ${identity.abi}")
    println("APK SHA-256: ${identity.apkSha256}")
    println("Signer SHA-256: ${identity.signerSha256}")
    println("Compatibility: ${result.status} — ${result.reason}")
    result.resolvedDescriptors.forEach { (hookId, descriptor) ->
        println("Hook $hookId: $descriptor")
    }

    check(result.status == CompatibilityStatus.COMPATIBLE) { "APK did not match a registered profile" }
}

private fun analyzeCandidate(arguments: CandidateArguments) {
    val policy = AppCompatibilityPolicies.require(arguments.appId)
    require(arguments.targets.isFile) { "Target file does not exist: ${arguments.targets.absolutePath}" }
    require(arguments.apk.isFile) { "APK does not exist: ${arguments.apk.absolutePath}" }
    val targets = Json.decodeFromString<List<CompatibilityTarget>>(arguments.targets.readText())
    policy.validateTargets(targets)

    val identity = ApkIdentityInspector().inspect(arguments.apk)
    policy.validateIdentity(identity)
    policy.validateSourceUrl(arguments.sourceUrl)
    val checkedVersions = arguments.checkedVersions
    val matchingTargets = targets.filter {
        it.identity.packageName == identity.packageName && it.identity.abi == identity.abi &&
            it.identity.versionName == identity.versionName && it.identity.versionCode == identity.versionCode
    }
    require(matchingTargets.size <= 1) { "Multiple profiles register this app version" }

    val report = matchingTargets.singleOrNull()?.let { target ->
        val facts = DexFactReader.scan(listOf(arguments.apk), target.hooks.map { it.stringAnchor }.toSet())
        CandidateCompatibilityAnalyzer.analyzeRegistered(
            identity = identity,
            target = target,
            requiredHookIds = policy.requiredHookIds,
            facts = facts,
            checkedVersions = checkedVersions,
            regressionPassed = arguments.regressionPassed,
            profileMergedToMain = arguments.profileMergedToMain,
            sourceUrl = arguments.sourceUrl,
        )
    } ?: run {
        val baseline = targets
            .filter {
                it.verificationStatus.runtimeVerified &&
                    it.identity.packageName == identity.packageName &&
                    it.identity.abi == identity.abi &&
                    it.identity.signerSha256.equals(identity.signerSha256, ignoreCase = true) &&
                    it.identity.versionCode < identity.versionCode
            }
            .maxByOrNull { it.identity.versionCode }

        if (baseline == null) {
            baselineMissingReport(identity, checkedVersions, arguments.sourceUrl, arguments.appId)
        } else {
            val facts = DexFactReader.scan(listOf(arguments.apk), baseline.hooks.map { it.stringAnchor }.toSet())
            CandidateCompatibilityAnalyzer.analyze(
                identity = identity,
                baseline = baseline,
                requiredHookIds = policy.requiredHookIds,
                facts = facts,
                checkedVersions = checkedVersions,
                regressionPassed = arguments.regressionPassed,
                sourceUrl = arguments.sourceUrl,
            )
        }
    }

    val appReport = report.copy(appId = arguments.appId)
    CandidateReportWriter.write(appReport, arguments.report)
    appendGithubOutput(report.status)
    println("Pipeline status: ${report.status}")
    report.hooks.forEach { hook ->
        val detail = hook.selectedDescriptor ?: hook.candidateDescriptors.joinToString().ifEmpty { hook.message }
        println("Hook ${hook.hookId}: ${hook.status} ($detail)")
    }
    report.blockers.forEach { blocker -> println("Blocked: $blocker") }
}

private fun baselineMissingReport(
    identity: io.github.nku100.wechatpad.compat.BuildIdentity,
    checkedVersions: List<String>,
    sourceUrl: String,
    appId: String,
): CandidateCompatibilityReport {
    var status = CandidatePipelineStatus.DISCOVERED
    status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.APK_FETCHED)
    status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.IDENTITY_ACCEPTED)
    status = CandidatePipelineStateMachine.transition(status, CandidatePipelineEvent.BASELINE_REJECTED)
    return CandidateCompatibilityReport(
        appId = appId,
        identity = identity,
        sourceUrl = sourceUrl,
        baselineVersion = null,
        checkedVersions = checkedVersions,
        status = status,
        blockers = listOf("No earlier formally supported build is available as an adaptation baseline"),
    )
}

private fun appendGithubOutput(status: CandidatePipelineStatus) {
    val outputPath = System.getenv("GITHUB_OUTPUT")?.takeIf(String::isNotBlank) ?: return
    FileWriter(outputPath, true).use { output -> output.append("pipeline_status=${status.name}\n") }
}

private fun parseArguments(args: Array<String>): CheckArguments {
    require(args.firstOrNull() == "check") { "Usage: check --targets <targets.json> --apk <apk-path>" }
    val options = args.drop(1).chunked(2)
    require(options.all { it.size == 2 && it.first().startsWith("--") }) {
        "Expected --targets <targets.json> and --apk <apk-path>"
    }
    val values = options.associate { it[0] to it[1] }
    val allowed = setOf("--targets", "--apk", "--app-id")
    require(values.keys.containsAll(setOf("--targets", "--apk")) && values.keys.all { it in allowed }) {
        "Expected --targets <targets.json>, --apk <apk-path>, and optional --app-id <id>"
    }
    return CheckArguments(
        targets = File(values.getValue("--targets")),
        apk = File(values.getValue("--apk")),
        appId = values["--app-id"] ?: "wechat",
    )
}

private fun parseCandidateArguments(args: Array<String>): CandidateArguments {
    val requiredKeys = setOf(
        "--targets",
        "--apk",
        "--source-url",
        "--checked-versions",
        "--regression-passed",
        "--report",
    )
    val allowedKeys = requiredKeys + setOf("--profile-merged-to-main", "--app-id")
    require(args.firstOrNull() == "analyze-candidate") {
        "Usage: analyze-candidate --targets <targets.json> --apk <apk-path> --source-url <url> " +
            "--checked-versions <comma-separated-versions> --regression-passed <true|false> --report <report.json>"
    }
    val options = args.drop(1).chunked(2)
    require(options.all { it.size == 2 && it.first().startsWith("--") }) {
        "Expected option/value pairs for analyze-candidate"
    }
    val values = options.associate { it[0] to it[1] }
    require(values.size == options.size) { "Duplicate analyze-candidate option" }
    require(values.keys.containsAll(requiredKeys) && values.keys.all { it in allowedKeys }) {
        "Expected --targets, --apk, --source-url, --checked-versions, --regression-passed, and --report"
    }
    val regressionPassed = values.getValue("--regression-passed").toBooleanStrictOrNull()
        ?: error("--regression-passed must be true or false")
    val profileMergedToMain = values["--profile-merged-to-main"]?.let { value ->
        value.toBooleanStrictOrNull() ?: error("--profile-merged-to-main must be true or false")
    } ?: false
    return CandidateArguments(
        targets = File(values.getValue("--targets")),
        apk = File(values.getValue("--apk")),
        sourceUrl = values.getValue("--source-url"),
        checkedVersions = values.getValue("--checked-versions").split(',').map(String::trim).filter(String::isNotEmpty),
        regressionPassed = regressionPassed,
        profileMergedToMain = profileMergedToMain,
        report = File(values.getValue("--report")),
        appId = values["--app-id"] ?: "wechat",
    )
}

private data class CheckArguments(val targets: File, val apk: File, val appId: String)

private data class CandidateArguments(
    val targets: File,
    val apk: File,
    val sourceUrl: String,
    val checkedVersions: List<String>,
    val regressionPassed: Boolean,
    val profileMergedToMain: Boolean,
    val report: File,
    val appId: String,
)
