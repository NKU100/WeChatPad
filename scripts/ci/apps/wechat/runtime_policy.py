"""WeChat-specific UI assertions used by the shared runtime smoke runner."""
import re
import xml.etree.ElementTree as ET

hook_installation_log = "installed 2 WeChat hooks"
login_input_activity = "MobileInputUI"
login_navigation_labels = (
    "log in", "login", "log in via mobile number", "log in with phone number",
    "log in on tablet only", "agree", "accept", "allow", "while using the app",
    "登录", "手机号登录", "同意",
)


def has_app_ui(xml, package_name):
    try:
        nodes = list(ET.fromstring(xml).iter("node"))
    except ET.ParseError:
        return False
    return any(node.get("package") == package_name for node in nodes)


def tablet_entry_visible(text):
    return bool(re.search(r"(?:log(?:ged)?\s*in|登录).*(?:phone\s*&\s*tablet|平板)", text, re.I))


def login_input_ready(activity, xml, package_name):
    return login_input_activity in activity and has_app_ui(xml, package_name)


def is_login_navigation_label(text):
    return text.strip().lower() in login_navigation_labels


def qr_page_ready(activity, xml, package_name, page_activity):
    try:
        nodes = list(ET.fromstring(xml).iter("node"))
    except ET.ParseError:
        return False
    return (page_activity in activity and any(node.get("package") == package_name for node in nodes)
            and any(re.search(r"QR\s*code|二维码", node.get("text", ""), re.I) for node in nodes))


def hook_diagnostics(logs):
    records = [line for line in logs.splitlines()
               if "WeChatPad" in line and "process skipped:" not in line
               and any(marker in line for marker in ["status=", "waiting for Tinker",
                                                       "resolved tablet=", hook_installation_log])]
    compatible = any("status=COMPATIBLE" in line for line in records)
    installed = any(hook_installation_log in line for line in records)
    descriptors = [line.split("resolved ", 1)[1] for line in records if "resolved tablet=" in line]
    return {
        "moduleLoaded": "OBSERVED" if records else "NOT_OBSERVED",
        "compatibility": "COMPATIBLE" if compatible else "NOT_OBSERVED",
        "hookInstallation": "INSTALLED_2" if installed else "NOT_OBSERVED",
        "resolvedHooks": list(dict.fromkeys(descriptors)),
        "records": list(dict.fromkeys(records))[-12:],
    }
