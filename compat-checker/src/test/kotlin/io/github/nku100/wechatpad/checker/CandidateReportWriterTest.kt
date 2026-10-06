package io.github.nku100.wechatpad.checker

import io.github.nku100.wechatpad.compat.BuildIdentity
import io.github.nku100.wechatpad.compat.CandidateCompatibilityReport
import io.github.nku100.wechatpad.compat.CandidateHookDiagnostic
import io.github.nku100.wechatpad.compat.CandidateHookStatus
import io.github.nku100.wechatpad.compat.CandidatePipelineStatus
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

class CandidateReportWriterTest {
    @Test
    fun writesAndReadsTheMachineReadablePipelineResult() {
        val report = CandidateCompatibilityReport(
            identity = BuildIdentity(
                packageName = "com.tencent.mm",
                versionName = "8.0.79",
                versionCode = 3200,
                abi = "arm64-v8a",
                apkSha256 = "a".repeat(64),
                signerSha256 = "b".repeat(64),
            ),
            sourceUrl = "https://dldir1v6.qq.com/weixin/android/weixin8079android3200_arm64.apk",
            baselineVersion = "8.0.69",
            checkedVersions = listOf("8.0.69", "8.0.79"),
            status = CandidatePipelineStatus.NEEDS_HOOK_REVIEW,
            hooks = listOf(
                CandidateHookDiagnostic(
                    hookId = "tablet",
                    stringAnchor = "Lenovo TB-9707F",
                    status = CandidateHookStatus.UNSAFE_ANCHOR,
                    candidateDescriptors = listOf("Lcom/tencent/mm/ui/other;->isLenovoTablet()Z"),
                    selectedDescriptor = "Lcom/tencent/mm/ui/other;->isLenovoTablet()Z",
                    message = "Anchor is unsafe to infer forward",
                ),
            ),
            blockers = listOf("Review the tablet hook anchor"),
        )
        val reportPath = Files.createTempDirectory("wechatpad-report-test").resolve("candidate-report.json")

        CandidateReportWriter.write(report, reportPath.toFile())

        val encoded = reportPath.toFile().readText()
        val decoded = Json.decodeFromString<CandidateCompatibilityReport>(encoded)
        assertEquals(report, decoded)
        assertTrue(encoded.contains("\"status\": \"NEEDS_HOOK_REVIEW\""))
        assertTrue(encoded.contains("\"apkSha256\": \"${"a".repeat(64)}\""))
    }

    @Test
    fun representsFetchFailureWithoutInventingAnApkIdentity() {
        val report = CandidateCompatibilityReport(
            identity = null,
            sourceUrl = null,
            baselineVersion = null,
            checkedVersions = emptyList(),
            status = CandidatePipelineStatus.FETCH_FAILED,
            blockers = listOf("Official APK download failed"),
        )
        val reportPath = Files.createTempDirectory("wechatpad-fetch-failure-test").resolve("candidate-report.json")

        CandidateReportWriter.write(report, reportPath.toFile())

        val decoded = Json.decodeFromString<CandidateCompatibilityReport>(reportPath.toFile().readText())
        assertEquals(report, decoded)
        assertTrue(reportPath.toFile().readText().contains("\"identity\": null"))
    }
}
