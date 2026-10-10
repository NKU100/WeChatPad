package io.github.nku100.impad.runtime

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class TargetMethodResolverTest {
    @Test
    fun resolvesObjectPrimitiveAndArrayDescriptors() {
        val descriptor = "L${DescriptorFixture::class.java.name.replace('.', '/')};" +
            "->sample(Ljava/lang/Object;I[Ljava/lang/String;[Z)Ljava/util/List;"

        val method = TargetMethodResolver.resolve(javaClass.classLoader!!, descriptor)

        assertEquals("sample", method.name)
        assertEquals(
            listOf(Any::class.java, Int::class.javaPrimitiveType, Array<String>::class.java, BooleanArray::class.java),
            method.parameterTypes.toList(),
        )
        assertEquals(List::class.java, method.returnType)
    }

    @Test
    fun resolvesPrimitiveReturnDescriptors() {
        val descriptor = "L${DescriptorFixture::class.java.name.replace('.', '/')};->count(J)D"

        val method = TargetMethodResolver.resolve(javaClass.classLoader!!, descriptor)

        assertEquals(Long::class.javaPrimitiveType, method.parameterTypes.single())
        assertEquals(Double::class.javaPrimitiveType, method.returnType)
    }

    @Test
    fun rejectsAMissingMethod() {
        val descriptor = "L${DescriptorFixture::class.java.name.replace('.', '/')};->missing()V"

        assertFailsWith<IllegalArgumentException> {
            TargetMethodResolver.resolve(javaClass.classLoader!!, descriptor)
        }
    }

    class DescriptorFixture {
        fun sample(value: Any, count: Int, names: Array<String>, flags: BooleanArray): List<String> =
            if (value.hashCode() >= 0 && count >= 0 && flags.isNotEmpty()) names.toList() else emptyList()

        fun count(value: Long): Double = value.toDouble()
    }
}
