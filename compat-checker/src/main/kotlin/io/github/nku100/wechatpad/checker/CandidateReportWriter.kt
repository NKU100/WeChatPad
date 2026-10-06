package io.github.nku100.wechatpad.checker

import io.github.nku100.wechatpad.compat.CandidateCompatibilityReport
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

object CandidateReportWriter {
    private val json = Json {
        prettyPrint = true
        encodeDefaults = true
    }

    fun write(report: CandidateCompatibilityReport, destination: File) {
        val absolutePath = destination.absoluteFile.toPath()
        val parent = requireNotNull(absolutePath.parent)
        Files.createDirectories(parent)
        val temporary = Files.createTempFile(parent, ".${destination.name}-", ".tmp")
        try {
            Files.writeString(temporary, encode(report))
            try {
                Files.move(temporary, absolutePath, ATOMIC_MOVE, REPLACE_EXISTING)
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(temporary, absolutePath, REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(temporary)
        }
    }

    fun encode(report: CandidateCompatibilityReport): String = json.encodeToString(report) + "\n"
}
