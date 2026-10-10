package io.github.nku100.impad.apps.wechat

import io.github.nku100.impad.runtime.HookCallback
import io.github.nku100.impad.runtime.HookInstaller
import io.github.nku100.impad.runtime.HookRegistrar
import io.github.nku100.impad.runtime.HookSpec
import io.github.nku100.impad.runtime.InstallOutcome
import java.lang.reflect.Method

class WeChatHookInstaller(
    registrar: HookRegistrar,
    private val callbacks: WeChatHookCallbacks = WeChatHookCallbacks(),
) {
    private val installer = HookInstaller(registrar)

    fun install(tabletMethod: Method, loginMethod: Method): InstallOutcome = installer.install(
        listOf(
            HookSpec(tabletMethod, "wechatpad_tablet", HookCallback(callbacks::tabletDetection)),
            HookSpec(loginMethod, "wechatpad_login", HookCallback(callbacks::loginEntry)),
        ),
    )
}
