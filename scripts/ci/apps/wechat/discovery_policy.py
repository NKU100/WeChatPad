"""Official WeChat release discovery strategy."""
from scripts.ci.discover_latest_wechat import discover_from_html, fetch_official_page


def discover(policy):
    return discover_from_html(fetch_official_page(), policy.official_apk_prefix)
