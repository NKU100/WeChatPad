package io.github.nku100.impad.runtime

import java.lang.reflect.Method

object TargetMethodResolver {
    fun resolve(classLoader: ClassLoader, descriptor: String): Method {
        val parsed = parse(descriptor)
        val declaringClass = classLoader.loadClass(parsed.className)
        val parameterTypes = parsed.parameterDescriptors.map { resolveType(classLoader, it) }.toTypedArray()
        val returnType = resolveType(classLoader, parsed.returnDescriptor)
        return declaringClass.declaredMethods.singleOrNull { method ->
            method.name == parsed.methodName &&
                method.returnType == returnType &&
                method.parameterTypes.contentEquals(parameterTypes)
        } ?: throw IllegalArgumentException("Method descriptor did not resolve uniquely: $descriptor")
    }

    private fun parse(descriptor: String): ParsedMethod {
        val separator = descriptor.indexOf("->")
        val openParameters = descriptor.indexOf('(', startIndex = separator + 2)
        val closeParameters = descriptor.indexOf(')', startIndex = openParameters + 1)
        require(separator > 1 && openParameters > separator + 2 && closeParameters > openParameters) {
            "Invalid method descriptor: $descriptor"
        }
        val classDescriptor = descriptor.substring(0, separator)
        require(classDescriptor.startsWith('L') && classDescriptor.endsWith(';')) {
            "Invalid declaring class descriptor: $descriptor"
        }
        val methodName = descriptor.substring(separator + 2, openParameters)
        require(methodName.isNotBlank()) { "Missing method name: $descriptor" }

        val parameters = parseParameterDescriptors(descriptor.substring(openParameters + 1, closeParameters))
        val returnDescriptor = descriptor.substring(closeParameters + 1)
        require(isSingleTypeDescriptor(returnDescriptor, allowVoid = true)) {
            "Invalid return descriptor: $descriptor"
        }
        return ParsedMethod(
            className = classDescriptor.substring(1, classDescriptor.length - 1).replace('/', '.'),
            methodName = methodName,
            parameterDescriptors = parameters,
            returnDescriptor = returnDescriptor,
        )
    }

    private fun parseParameterDescriptors(descriptors: String): List<String> {
        val types = mutableListOf<String>()
        var index = 0
        while (index < descriptors.length) {
            val start = index
            while (descriptors[index] == '[') index++
            require(index < descriptors.length) { "Invalid parameter descriptor: $descriptors" }
            if (descriptors[index] == 'L') {
                index = descriptors.indexOf(';', startIndex = index)
                require(index >= 0) { "Invalid parameter descriptor: $descriptors" }
                index++
            } else {
                require(descriptors[index] in PRIMITIVE_DESCRIPTORS) {
                    "Invalid parameter descriptor: $descriptors"
                }
                index++
            }
            types += descriptors.substring(start, index)
        }
        return types
    }

    private fun isSingleTypeDescriptor(descriptor: String, allowVoid: Boolean): Boolean {
        if (allowVoid && descriptor == "V") return true
        return try {
            val parsed = parseParameterDescriptors(descriptor)
            parsed.size == 1 && parsed.single() == descriptor
        } catch (_: IllegalArgumentException) {
            false
        }
    }

    private fun resolveType(classLoader: ClassLoader, descriptor: String): Class<*> = when (descriptor) {
        "Z" -> Boolean::class.javaPrimitiveType!!
        "B" -> Byte::class.javaPrimitiveType!!
        "C" -> Char::class.javaPrimitiveType!!
        "S" -> Short::class.javaPrimitiveType!!
        "I" -> Int::class.javaPrimitiveType!!
        "J" -> Long::class.javaPrimitiveType!!
        "F" -> Float::class.javaPrimitiveType!!
        "D" -> Double::class.javaPrimitiveType!!
        "V" -> Void.TYPE
        else -> when {
            descriptor.startsWith('L') && descriptor.endsWith(';') ->
                classLoader.loadClass(descriptor.substring(1, descriptor.length - 1).replace('/', '.'))

            descriptor.startsWith('[') -> Class.forName(descriptor.replace('/', '.'), false, classLoader)
            else -> throw IllegalArgumentException("Invalid type descriptor: $descriptor")
        }
    }

    private data class ParsedMethod(
        val className: String,
        val methodName: String,
        val parameterDescriptors: List<String>,
        val returnDescriptor: String,
    )

    private const val PRIMITIVE_DESCRIPTORS = "ZBCSIJFD"
}
