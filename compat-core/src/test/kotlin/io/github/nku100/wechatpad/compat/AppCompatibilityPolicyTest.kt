package io.github.nku100.wechatpad.compat

import java.io.File
import kotlin.test.Test
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

class AppCompatibilityPolicyTest {
    @Test
    fun validatesASecondPolicyWithoutWeChatPackageAbiOrHookAssumptions() {
        val policy = AppCompatibilityPolicy(
            appId = "testapp",
            packageName = "org.example.testapp",
            supportedAbis = setOf("x86_64"),
            signerSha256 = SIGNER,
            requiredHookIds = setOf("route", "session"),
            officialApkPrefix = "https://downloads.example.org/testapp/",
            targetsPath = "compatibility/testapp/targets.json",
        )
        policy.validateTargets(listOf(target()))
        policy.validateIdentity(target().identity)
        policy.validateSourceUrl("https://downloads.example.org/testapp/candidate.apk")

        assertFailsWith<IllegalArgumentException> {
            policy.validateTargets(listOf(target().copy(hooks = target().hooks.take(1))))
        }
    }

    @Test
    fun productionRegistryRejectsUnknownApplications() {
        val error = assertFailsWith<IllegalArgumentException> { AppCompatibilityPolicies.require("qq") }
        assertTrue(error.message!!.contains("Unknown or unregistered appId"))
    }

    @Test
    fun registeredWeChatPolicyAcceptsTheUnmodifiedProductionManifest() {
        val manifest = listOf(File("compatibility/wechat/targets.json"), File("../compatibility/wechat/targets.json"))
            .firstOrNull(File::isFile)
        assertNotNull(manifest, "Production WeChat targets are available to core tests")
        val targets = Json.decodeFromString<List<CompatibilityTarget>>(manifest.readText())
        AppCompatibilityPolicies.require("wechat").validateTargets(targets)
        assertNotNull(targets.singleOrNull { it.identity.versionName == "8.0.79" })
    }

    @Test
    fun permitsDistinctDigestsAtTheSameVersionAndRejectsCaseInsensitiveDuplicates() {
        val policy = AppCompatibilityPolicies.require("wechat")
        val first = productionTarget("a".repeat(64))
        val repack = productionTarget("b".repeat(64))
        policy.validateTargets(listOf(first, repack))

        val duplicate = productionTarget("A".repeat(64))
        assertFailsWith<IllegalArgumentException> {
            policy.validateTargets(listOf(first, duplicate))
        }
    }

    private fun productionTarget(digest: String) = CompatibilityTarget(
        identity = BuildIdentity("com.tencent.mm", "8.0.79", 3200, "arm64-v8a", digest,
            "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c"),
        featureRulesVersion = 1,
        hooks = listOf(
            HookRule("tablet", "tablet", emptyList(), "Z", "Lfixture/Tablet;->check()Z"),
            HookRule("login", "login", emptyList(), "V", "Lfixture/Login;->open()V"),
        ),
        sourceUrl = "https://dldir1v6.qq.com/weixin/android/repack.apk",
    )

    private fun target() = CompatibilityTarget(
        identity = BuildIdentity(
            packageName = "org.example.testapp",
            versionName = "2.4",
            versionCode = 24,
            abi = "x86_64",
            apkSha256 = APK,
            signerSha256 = SIGNER,
        ),
        featureRulesVersion = 1,
        hooks = listOf(
            HookRule("route", "route", emptyList(), "V", "Lfixture/Route;->run()V"),
            HookRule("session", "session", emptyList(), "Z", "Lfixture/Session;->valid()Z"),
        ),
        sourceUrl = "https://downloads.example.org/testapp/base.apk",
    )

    private companion object {
        val APK = "a".repeat(64)
        val SIGNER = "b".repeat(64)
    }
}
