import org.gradle.api.tasks.JavaExec

plugins {
    alias(libs.plugins.kotlin.jvm)
    application
}

kotlin {
    jvmToolchain(21)
}

application {
    mainClass = "io.github.nku100.wechatpad.checker.MainKt"
}

tasks.named<JavaExec>("run") {
    workingDir = rootProject.projectDir
}

dependencies {
    implementation(project(":compat-core"))
    implementation(libs.kotlinx.serialization.json)
    testImplementation(kotlin("test"))
}
