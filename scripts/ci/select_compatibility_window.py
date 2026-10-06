import argparse
import json
import re
from pathlib import Path


SUPPORTED_STATUS = "runtime-verified-local"


def select_regression_targets(targets: list[dict], candidate_version_code: int) -> list[dict]:
    if type(candidate_version_code) is not int or candidate_version_code <= 0:
        raise ValueError("candidate version code must be a positive integer")

    seen_version_codes: set[int] = set()
    supported: list[tuple[int, dict]] = []
    for target in targets:
        identity = target.get("identity")
        if not isinstance(identity, dict):
            raise ValueError("target identity must be an object")
        version_code = identity.get("versionCode")
        if type(version_code) is not int or version_code <= 0:
            raise ValueError("target version code must be a positive integer")
        if version_code in seen_version_codes:
            raise ValueError(f"duplicate version code in compatibility targets: {version_code}")
        seen_version_codes.add(version_code)
        if target.get("verificationStatus") == SUPPORTED_STATUS:
            supported.append((version_code, target))

    supported.sort(key=lambda item: item[0])
    if supported and candidate_version_code < supported[-1][0]:
        raise ValueError("candidate version code is below the latest formally supported build")

    candidate_is_supported = any(code == candidate_version_code for code, _ in supported)
    if candidate_is_supported:
        return [target for _, target in supported[-3:]]

    predecessors = [target for code, target in supported if code < candidate_version_code]
    return predecessors[-2:]


def matrix_entries(targets: list[dict]) -> list[dict[str, object]]:
    entries = []
    for target in targets:
        identity = target["identity"]
        raw_digest = identity.get("apkSha256")
        digest = raw_digest.lower() if isinstance(raw_digest, str) else ""
        source_url = target.get("sourceUrl", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("selected target has an invalid APK SHA-256")
        if not source_url.startswith("https://dldir1v6.qq.com/weixin/android/") or not source_url.endswith(".apk"):
            raise ValueError("selected target source URL is outside the official Tencent CDN APK directory")
        entries.append({
            "version_name": identity["versionName"],
            "version_code": identity["versionCode"],
            "sha256": digest,
            "source_url": source_url,
        })
    return entries


def append_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"GitHub Actions output {key} contains a newline")
            output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--candidate-version-code", type=int, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    arguments = parser.parse_args()

    targets = json.loads(arguments.targets.read_text(encoding="utf-8"))
    selected = select_regression_targets(targets, arguments.candidate_version_code)
    matrix = matrix_entries(selected)
    append_github_output(arguments.github_output, {
        "matrix": json.dumps(matrix, separators=(",", ":")),
        "regression_versions": ",".join(str(entry["version_name"]) for entry in matrix),
    })
    print(f"Selected regression targets: {', '.join(str(row['version_name']) for row in matrix) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
