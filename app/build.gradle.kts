import java.io.File
import java.util.Properties
import java.util.zip.ZipFile
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.testing.Test

plugins {
    alias(libs.plugins.android.app)
}

abstract class GenerateCompatibilityTargets : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFile: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val destination = outputDirectory.file("compatibility/targets.json").get().asFile
        destination.parentFile.mkdirs()
        sourceFile.get().asFile.copyTo(destination, overwrite = true)
    }
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

androidComponents {
    onVariants(selector().all()) { variant ->
        val task = tasks.register<GenerateCompatibilityTargets>(
            "generate${variant.name.replaceFirstChar(Char::uppercase)}CompatibilityTargets",
        ) {
            sourceFile.set(rootProject.layout.projectDirectory.file("compatibility/targets.json"))
            outputDirectory.set(layout.buildDirectory.dir("generated/compatibility-assets/${variant.name}"))
        }
        checkNotNull(variant.sources.assets).addGeneratedSourceDirectory(
            task,
            GenerateCompatibilityTargets::outputDirectory,
        )
    }
}

dependencies {
    compileOnly(libs.libxposed.api)
    implementation(project(":compat-core"))
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.junit.jupiter)
    testImplementation(kotlin("test"))
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
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

            val targetEntries = archive.entries().asSequence()
                .filter { it.name == "assets/compatibility/targets.json" }
                .toList()
            check(targetEntries.size == 1) {
                "Expected exactly one packaged compatibility profile file, found ${targetEntries.size}"
            }
            val packagedTargets = archive.getInputStream(targetEntries.single()).use { it.readBytes() }
            val sourceTargets = rootProject.file("compatibility/targets.json").readBytes()
            check(packagedTargets.contentEquals(sourceTargets)) {
                "Packaged compatibility profiles differ from compatibility/targets.json"
            }
        }
    }
}
