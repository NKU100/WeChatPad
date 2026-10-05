import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


OFFICIAL_PAGE = "https://weixin.qq.com/"
OFFICIAL_HOST = "dldir1v6.qq.com"
DOWNLOAD_PATH = "/weixin/android/"
USER_AGENT = "WeChatPadCompatibilityChecker/1.0"
MAX_PAGE_BYTES = 5_000_000
APK_URL_PATTERN = re.compile(
    r"https://dldir1v6[.]qq[.]com/weixin/android/[A-Za-z0-9._-]+[.]apk",
    re.IGNORECASE,
)
ARM64_FILENAME_PATTERN = re.compile(
    r"weixin(?P<build>\d{4})android(?P<version_code>\d+)"
    r"(?:_[A-Za-z0-9.-]+)*_arm64(?:_[A-Za-z0-9.-]+)?[.]apk",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    url: str
    filename: str
    build_number: int
    version_code: int


def validate_official_apk_url(url: str) -> None:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Invalid official Tencent CDN URL") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != OFFICIAL_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.startswith(DOWNLOAD_PATH)
        or not re.fullmatch(r"/weixin/android/[A-Za-z0-9._-]+[.]apk", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("URL is outside the official Tencent CDN APK directory")


def discover_from_html(page_html: str) -> Candidate:
    normalized_html = html.unescape(page_html).replace("\\/", "/")
    urls = set(APK_URL_PATTERN.findall(normalized_html))
    candidates: dict[str, Candidate] = {}

    for url in urls:
        validate_official_apk_url(url)
        filename = urlsplit(url).path.rsplit("/", 1)[-1]
        match = ARM64_FILENAME_PATTERN.fullmatch(filename)
        if match is None:
            continue
        candidates[url] = Candidate(
            url=url,
            filename=filename,
            build_number=int(match.group("build")),
            version_code=int(match.group("version_code")),
        )

    if not candidates:
        raise ValueError("Official page contains no ARM64 APK candidates")

    latest_rank = max((item.build_number, item.version_code) for item in candidates.values())
    latest = [item for item in candidates.values() if (item.build_number, item.version_code) == latest_rank]
    if len(latest) != 1:
        names = ", ".join(sorted(item.filename for item in latest))
        raise ValueError(f"Official page has ambiguous highest ARM64 APK candidates: {names}")
    return latest[0]


def fetch_official_page() -> str:
    request = Request(OFFICIAL_PAGE, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        final_url = urlsplit(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != "weixin.qq.com":
            raise ValueError("Official download page redirected outside weixin.qq.com")
        if response.status != 200:
            raise ValueError(f"Official download page returned HTTP {response.status}")
        page = response.read(MAX_PAGE_BYTES + 1)
    if len(page) > MAX_PAGE_BYTES:
        raise ValueError("Official download page exceeded the 5 MB safety limit")
    return page.decode("utf-8", errors="replace")


def expected_sha256_for_url(targets_path: Path, source_url: str) -> str:
    targets = json.loads(targets_path.read_text(encoding="utf-8"))
    matches = [target for target in targets if target.get("sourceUrl") == source_url]
    if len(matches) > 1:
        raise ValueError("Multiple compatibility profiles register the discovered APK URL")
    if not matches:
        return ""
    expected = matches[0]["identity"].get("apkSha256", "").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Registered APK URL has an invalid SHA-256 digest")
    return expected


def append_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"GitHub Actions output {key} contains a newline")
            output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()

    try:
        candidate = discover_from_html(fetch_official_page())
        expected_sha256 = expected_sha256_for_url(arguments.targets, candidate.url)
        url_sha256 = hashlib.sha256(candidate.url.encode("utf-8")).hexdigest()
        cache_dir = f".cache/wechatpad-latest/{url_sha256}"
        outputs = {
            "source_url": candidate.url,
            "filename": candidate.filename,
            "build_number": str(candidate.build_number),
            "version_code_hint": str(candidate.version_code),
            "expected_sha256": expected_sha256,
            "url_sha256": url_sha256,
            "cache_dir": cache_dir,
            "cache_key": f"wechatpad-latest-url-{url_sha256}",
        }
        append_github_output(arguments.github_output, outputs)
        with arguments.report.open("a", encoding="utf-8") as report:
            report.write("## Official latest ARM64 APK\n\n")
            report.write(f"Filename: {candidate.filename}\n\nSource: {candidate.url}\n\n")
            if expected_sha256:
                report.write(f"Registered APK SHA-256: {expected_sha256}\n\n")
            else:
                report.write("This build is not yet registered in the compatibility manifest.\n\n")
        print(f"Selected official ARM64 APK: {candidate.filename}")
        return 0
    except Exception as error:
        message = f"Official latest WeChat discovery failed: {error}"
        print(message, file=sys.stderr)
        with arguments.report.open("a", encoding="utf-8") as report:
            report.write(f"\nDiscovery failed: {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
