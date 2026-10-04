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

dependencies {
    implementation(project(":compat-core"))
    testImplementation(kotlin("test"))
}
