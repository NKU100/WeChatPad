import java.io.File
import java.util.Properties
import java.util.zip.ZipFile

plugins {
    alias(libs.plugins.android.app)
}

android {
    namespace = "io.github.nku100.wechatpad"
    compileSdk = 37
    compileSdkMinor = 2
    buildToolsVersion = "37.0.0"

    defaultConfig {
        applicationId = "io.github.nku100.wechatpad"
        minSdk = 28
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }

    packaging {
        resources {
            merges += "META-INF/xposed/*"
        }
    }
}

dependencies {
    compileOnly(libs.libxposed.api)
    implementation(project(":compat-core"))
    testImplementation(kotlin("test"))
}

tasks.register("verifyModuleMetadata") {
    dependsOn("assembleDebug")

    doLast {
        val apk = layout.buildDirectory.file("outputs/apk/debug/app-debug.apk").get().asFile
        check(apk.isFile) { "Debug APK was not produced: $apk" }

        val sdkPath = System.getenv("ANDROID_HOME")
            ?: rootProject.file("local.properties").takeIf(File::isFile)?.let { localPropertiesFile ->
                Properties().apply { localPropertiesFile.inputStream().use(::load) }
                    .getProperty("sdk.dir")
            }
            ?: error("Set ANDROID_HOME or sdk.dir to inspect the packaged APK")
        val apkanalyzer = File(sdkPath, "cmdline-tools/latest/bin/apkanalyzer")
        check(apkanalyzer.isFile) { "apkanalyzer was not found: $apkanalyzer" }

        val process = ProcessBuilder(
            apkanalyzer.absolutePath,
            "manifest",
            "application-id",
            apk.absolutePath,
        ).redirectErrorStream(true).start()
        val applicationId = process.inputStream.bufferedReader().use { it.readText() }.trim()
        check(process.waitFor() == 0) { "apkanalyzer failed: $applicationId" }
        check(applicationId == "io.github.nku100.wechatpad") {
            "Unexpected application id: $applicationId"
        }

        ZipFile(apk).use { archive ->
            val propertiesEntry = checkNotNull(archive.getEntry("META-INF/xposed/module.prop")) {
                "Module metadata is missing from the APK"
            }
            val module = Properties().apply {
                archive.getInputStream(propertiesEntry).use(::load)
            }
            check(module.getProperty("minApiVersion") == "102")
            check(module.getProperty("targetApiVersion") == "102")
            check(module.getProperty("staticScope") == "true")

            val scope = checkNotNull(archive.getEntry("META-INF/xposed/scope.list")) {
                "Module scope is missing from the APK"
            }
            val scopePackages = archive.getInputStream(scope).bufferedReader().use { reader ->
                reader.readLines().map(String::trim).filter(String::isNotEmpty)
            }
            check(scopePackages == listOf("com.tencent.mm")) {
                "Unexpected module scope: $scopePackages"
            }

            val entryPoint = checkNotNull(archive.getEntry("META-INF/xposed/java_init.list")) {
                "Module entry point is missing from the APK"
            }
            val entryClasses = archive.getInputStream(entryPoint).bufferedReader().use { reader ->
                reader.readLines().map(String::trim).filter(String::isNotEmpty)
            }
            check(entryClasses == listOf("io.github.nku100.wechatpad.WeChatPadModule")) {
                "Unexpected module entry point: $entryClasses"
            }
        }
    }
}
