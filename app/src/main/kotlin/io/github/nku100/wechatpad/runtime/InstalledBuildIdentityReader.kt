package io.github.nku100.wechatpad.runtime

import android.content.pm.ApplicationInfo
import io.github.nku100.wechatpad.compat.BuildIdentity
import java.io.File
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.zip.ZipFile

data class InstalledPackageMetadata(
    val packageName: String,
    val uid: Int,
    val apkFiles: List<File>,
    val dataDirectory: File,
)

data class InstalledBuild(
    val identity: BuildIdentity,
    val apkFiles: List<File>,
    val installFingerprint: String,
    val dataDirectory: File,
)

class InstalledBuildIdentityReader(
    private val supportedAbisProvider: () -> List<String> = { android.os.Build.SUPPORTED_ABIS.toList() },
) {
    fun read(applicationInfo: ApplicationInfo): InstalledBuild {
        val baseApkPath = checkNotNull(applicationInfo.sourceDir) { "WeChat source APK path was null" }
        val apkFiles = listOf(baseApkPath) + applicationInfo.splitSourceDirs.orEmpty()
        return read(
            InstalledPackageMetadata(
                packageName = applicationInfo.packageName.orEmpty(),
                uid = applicationInfo.uid,
                apkFiles = apkFiles.map(::File),
                dataDirectory = File(checkNotNull(applicationInfo.dataDir) { "WeChat data directory was null" }),
            ),
        )
    }

    fun read(metadata: InstalledPackageMetadata): InstalledBuild {
        require(metadata.apkFiles.isNotEmpty()) { "WeChat APK paths were empty" }
        require(metadata.apkFiles.all(File::isFile)) { "An installed WeChat APK path was missing" }

        val identity = BuildIdentity(
            packageName = metadata.packageName,
            versionName = "",
            versionCode = 0,
            abi = readAbi(metadata.apkFiles),
            apkSha256 = null,
            signerSha256 = "",
        )
        return InstalledBuild(
            identity = identity,
            apkFiles = metadata.apkFiles,
            installFingerprint = installFingerprint(metadata),
            dataDirectory = metadata.dataDirectory,
        )
    }

    fun sha256(apk: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        apk.inputStream().buffered().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().toHexString()
    }

    private fun readAbi(apkFiles: List<File>): String {
        val availableAbis = apkFiles.flatMap { apk ->
            ZipFile(apk).use { zip ->
                zip.entries().asSequence()
                    .filter { !it.isDirectory && it.name.endsWith(".so") }
                    .mapNotNull { entry ->
                        val parts = entry.name.split('/')
                        parts.getOrNull(1)?.takeIf { parts.firstOrNull() == "lib" }
                    }
                    .toList()
            }
        }.toSet()
        return supportedAbisProvider().firstOrNull(availableAbis::contains)
            ?: availableAbis.singleOrNull()
            ?: "unknown"
    }

    private fun installFingerprint(metadata: InstalledPackageMetadata): String {
        val details = buildString {
            append(metadata.packageName)
            append('|')
            append(metadata.uid)
            for (apk in metadata.apkFiles) {
                append('|')
                append(apk.absolutePath)
                append(':')
                append(apk.length())
                append(':')
                append(apk.lastModified())
            }
        }
        return MessageDigest.getInstance("SHA-256")
            .digest(details.toByteArray(StandardCharsets.UTF_8))
            .toHexString()
    }

    private fun ByteArray.toHexString(): String = joinToString("") { "%02x".format(it) }
}
