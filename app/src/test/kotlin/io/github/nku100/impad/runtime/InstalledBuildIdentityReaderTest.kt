package io.github.nku100.impad.runtime

import java.nio.file.Files
import java.util.Comparator
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.assertEquals
import kotlin.test.assertNull
import org.junit.jupiter.api.Test

class InstalledBuildIdentityReaderTest {
    @Test
    fun readsPackageAbiFilesAndAnInstallFingerprintWithoutHashing() = withFixture { directory, apk ->
        val reader = InstalledBuildIdentityReader(supportedAbisProvider = { listOf("arm64-v8a") })

        val build = reader.read(
            InstalledPackageMetadata(
                packageName = "com.tencent.mm",
                uid = 10234,
                apkFiles = listOf(apk),
                dataDirectory = directory.resolve("data").toFile(),
            ),
        )

        assertEquals("com.tencent.mm", build.identity.packageName)
        assertEquals("arm64-v8a", build.identity.abi)
        assertNull(build.identity.apkSha256)
        assertEquals("", build.identity.signerSha256)
        assertEquals(64, reader.sha256(apk).length)
        assertEquals(64, build.installFingerprint.length)
    }

    @Test
    fun changesTheFingerprintWhenTheInstalledApkPathChanges() = withFixture { directory, apk ->
        val reader = InstalledBuildIdentityReader(supportedAbisProvider = { listOf("arm64-v8a") })
        val first = reader.read(
            InstalledPackageMetadata(
                packageName = "com.tencent.mm",
                uid = 10234,
                apkFiles = listOf(apk),
                dataDirectory = directory.resolve("data").toFile(),
            ),
        )
        val replacement = directory.resolve("replacement.apk").toFile()
        Files.copy(apk.toPath(), replacement.toPath())
        val second = reader.read(
            InstalledPackageMetadata(
                packageName = "com.tencent.mm",
                uid = 10234,
                apkFiles = listOf(replacement),
                dataDirectory = directory.resolve("data").toFile(),
            ),
        )

        assertEquals(false, first.installFingerprint == second.installFingerprint)
    }

    private fun withFixture(block: (java.nio.file.Path, java.io.File) -> Unit) {
        val directory = Files.createTempDirectory("impad installed build")
        try {
            val apk = directory.resolve("base.apk").toFile()
            ZipOutputStream(Files.newOutputStream(apk.toPath())).use { zip ->
                zip.putNextEntry(ZipEntry("lib/arm64-v8a/libwechat.so"))
                zip.write(byteArrayOf(1, 2, 3))
                zip.closeEntry()
            }
            block(directory, apk)
        } finally {
            Files.walk(directory).use { paths ->
                paths.sorted(Comparator.reverseOrder<java.nio.file.Path>()).forEach(Files::deleteIfExists)
            }
        }
    }

}
