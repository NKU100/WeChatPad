package io.github.nku100.wechatpad.compat

import com.android.tools.smali.dexlib2.Opcodes
import com.android.tools.smali.dexlib2.dexbacked.DexBackedDexFile
import com.android.tools.smali.dexlib2.iface.Method
import com.android.tools.smali.dexlib2.iface.instruction.ReferenceInstruction
import com.android.tools.smali.dexlib2.iface.reference.StringReference
import java.io.BufferedInputStream
import java.io.File
import java.util.zip.ZipFile

object DexFactReader {
    private val dexEntryPattern = Regex("classes(\\d*)\\.dex")

    fun scan(apkFiles: List<File>, stringAnchors: Set<String>): List<DexMethodFact> {
        if (stringAnchors.isEmpty()) return emptyList()

        return buildList {
            for (apkFile in apkFiles) {
                ZipFile(apkFile).use { apk ->
                    val dexEntries = apk.entries().asSequence()
                        .filter { !it.isDirectory && dexEntryPattern.matches(it.name) }
                        .sortedBy { dexIndex(it.name) }
                        .toList()

                    for (entry in dexEntries) {
                        BufferedInputStream(apk.getInputStream(entry)).use { dexInput ->
                            val dex = DexBackedDexFile.fromInputStream(Opcodes.getDefault(), dexInput)
                            for (classDefinition in dex.classes) {
                                for (method in classDefinition.methods) {
                                    val implementation = method.implementation ?: continue
                                    val methodAnchors = buildSet {
                                        for (instruction in implementation.instructions) {
                                            val reference = (instruction as? ReferenceInstruction)?.reference
                                            val string = (reference as? StringReference)?.string
                                            if (string != null && string in stringAnchors) add(string)
                                        }
                                    }
                                    if (methodAnchors.isNotEmpty()) {
                                        add(method.toFact(methodAnchors))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private fun dexIndex(entryName: String): Int =
        dexEntryPattern.matchEntire(entryName)?.groupValues?.get(1)?.toIntOrNull() ?: 1

    private fun Method.toFact(strings: Set<String>): DexMethodFact = DexMethodFact(
        descriptor = buildString {
            append(definingClass)
            append("->")
            append(name)
            append('(')
            parameterTypes.forEach { append(it) }
            append(')')
            append(returnType)
        },
        parameterDescriptors = parameterTypes.map(CharSequence::toString),
        returnDescriptor = returnType,
        strings = strings,
    )
}
