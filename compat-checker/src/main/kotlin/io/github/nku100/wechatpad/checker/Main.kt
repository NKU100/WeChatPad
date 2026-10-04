package io.github.nku100.wechatpad.checker

import io.github.nku100.wechatpad.compat.CompatibilityResolver
import io.github.nku100.wechatpad.compat.CompatibilityStatus
import io.github.nku100.wechatpad.compat.CompatibilityTarget
import io.github.nku100.wechatpad.compat.DexFactReader
import io.github.nku100.wechatpad.compat.IdentityVerification
import java.io.File
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import kotlin.system.exitProcess

fun main(args: Array<String>) {
    try {
        checkCompatibility(parseArguments(args))
    } catch (error: Exception) {
        System.err.println("Compatibility check failed: ${error.message}")
        exitProcess(1)
    }
}

private fun checkCompatibility(arguments: CheckArguments) {
    require(arguments.targets.isFile) { "Target file does not exist: ${arguments.targets.absolutePath}" }
    val targets = Json.decodeFromString<List<CompatibilityTarget>>(arguments.targets.readText())
    require(targets.isNotEmpty()) { "Target file contains no compatibility targets" }

    val identity = ApkIdentityInspector().inspect(arguments.apk)
    val anchors = targets.flatMap { target -> target.hooks.map { it.stringAnchor } }.toSet()
    val facts = DexFactReader.scan(listOf(arguments.apk), anchors)
    val result = CompatibilityResolver.resolve(
        identity = identity,
        verification = IdentityVerification.STATIC_APK,
        targets = targets,
        facts = facts,
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

private fun parseArguments(args: Array<String>): CheckArguments {
    require(args.firstOrNull() == "check") { "Usage: check --targets <targets.json> --apk <apk-path>" }
    val options = args.drop(1).chunked(2)
    require(options.all { it.size == 2 && it.first().startsWith("--") }) {
        "Expected --targets <targets.json> and --apk <apk-path>"
    }
    val values = options.associate { it[0] to it[1] }
    require(values.keys == setOf("--targets", "--apk")) {
        "Expected --targets <targets.json> and --apk <apk-path>"
    }
    return CheckArguments(
        targets = File(values.getValue("--targets")),
        apk = File(values.getValue("--apk")),
    )
}

private data class CheckArguments(val targets: File, val apk: File)
