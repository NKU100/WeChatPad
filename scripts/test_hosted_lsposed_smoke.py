import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import subprocess
import tempfile
from contextlib import ExitStack, redirect_stdout
import io

spec = importlib.util.spec_from_file_location('smoke', Path(__file__).parent / 'ci/hosted_lsposed_smoke.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class UiEvidenceTest(unittest.TestCase):
    def test_page_size_backcompat_is_enabled_before_each_launch(self):
        with patch.object(smoke, "su") as root:
            smoke.enable_page_size_backcompat()
        self.assertEqual(root.call_args_list[0].args, ("setprop bionic.linker.16kb.app_compat.enabled true; setprop pm.16kb.app_compat.disabled false",))

    def test_snapshot_uses_native_hierarchy_reader(self):
        result = subprocess.CompletedProcess([], 0, b"<hierarchy />", b"")
        with tempfile.TemporaryDirectory() as folder, patch.object(smoke, "EVIDENCE", Path(folder)), patch.object(smoke, "adb", return_value=result) as device:
            smoke.snapshot("probe")
        self.assertTrue(any("UiHierarchy" in call.args for call in device.call_args_list))
        self.assertFalse(any("/sdcard/" in str(call.args) for call in device.call_args_list))

    def test_manager_and_module_are_installed_before_framework_reboot(self):
        events = []
        result = subprocess.CompletedProcess([], 0, b'123', b'')
        with ExitStack() as stack:
            folder = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(patch.object(smoke, 'EVIDENCE', Path(folder)))
            stack.enter_context(patch.object(smoke, 'adb', side_effect=lambda *args, **kwargs: (events.append(args), result)[1]))
            stack.enter_context(patch.object(smoke, 'su', return_value=result))
            stack.enter_context(patch.object(smoke, 'save'))
            stack.enter_context(patch.object(smoke, 'mobile_input', return_value='<hierarchy />'))
            stack.enter_context(patch.object(smoke, 'bootstrap_magisk'))
            stack.enter_context(patch.object(smoke, 'enable_page_size_backcompat'))
            stack.enter_context(patch.object(smoke, 'configure_manager'))
            stack.enter_context(patch.object(smoke, 'collect_logs', return_value=''))
            stack.enter_context(patch.object(smoke, 'snapshot', return_value=('', '')))
            stack.enter_context(patch.object(smoke, 'reboot', side_effect=lambda: events.append(('reboot',))))
            stack.enter_context(redirect_stdout(io.StringIO()))
            self.assertEqual(smoke.main(), 1)
        restart = events.index(('reboot',))
        for apk in ('manager.apk', 'module/app-debug.apk'):
            install = next((i for i, args in enumerate(events) if args[0] == 'install' and args[-1].endswith(apk)), None)
            self.assertIsNotNone(install, apk)
            self.assertLess(install, restart, apk)

    def test_launcher_is_not_wechat(self):
        self.assertFalse(smoke.has_wechat_ui('<hierarchy><node package="com.google.android.apps.nexuslauncher" /></hierarchy>'))

    def test_wechat_ui_is_recognized(self):
        self.assertTrue(smoke.has_wechat_ui('<hierarchy><node package="com.tencent.mm" /></hierarchy>'))

    def test_tablet_entry_requires_explicit_login_choice(self):
        self.assertFalse(smoke.is_tablet_entry('Use a tablet to read more'))
        self.assertTrue(smoke.is_tablet_entry('Logged in on Phone & Tablet'))

    def test_qr_requires_activity_and_rendered_wechat_instructions(self):
        ui = '<hierarchy><node package="com.tencent.mm" text="Scan the QR code with WeChat" /></hierarchy>'
        self.assertFalse(smoke.qr_page_ready('topResumedActivity=com.tencent.mm/.app.WeChatSplashActivity', ui))
        self.assertTrue(smoke.qr_page_ready('topResumedActivity=com.tencent.mm/.plugin.account.ui.LoginAsExDeviceUI', ui))
        self.assertFalse(smoke.qr_page_ready('topResumedActivity=com.tencent.mm/.plugin.account.ui.LoginAsExDeviceUI', '<hierarchy />'))

    def test_click_target_must_be_unique(self):
        xml = '<hierarchy><node text="Modules" bounds="[0,0][10,10]"/><node text="Modules" bounds="[10,10][20,20]"/></hierarchy>'
        with self.assertRaises(ValueError):
            smoke.unique_node(xml, lambda node: node.get('text') == 'Modules')


if __name__ == '__main__':
    unittest.main()
