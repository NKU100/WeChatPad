import argparse
import json
import re
from pathlib import Path
from typing import Optional

from scripts.ci.app_policy import get_policy


SUPPORTED_STATUSES = {"runtime-verified-local", "runtime-verified-hosted"}


def select_regression_targets(
    targets: list[dict], candidate_version_code: int, app_id: Optional[str] = None,
    package_name: Optional[str] = None, abi: Optional[str] = None,
) -> list[dict]:
    if type(candidate_version_code) is not int or candidate_version_code <= 0:
        raise ValueError("candidate version code must be a positive integer")

    policy = get_policy(app_id)
    package_name = package_name or policy.package_name
    if abi is None:
        compatible_abis = {row.get("identity", {}).get("abi") for row in targets
                           if row.get("identity", {}).get("packageName") == package_name}
        compatible_abis.discard(None)
        if len(compatible_abis) != 1:
            raise ValueError("Compatibility window requires one explicit package and ABI")
        abi = compatible_abis.pop()
    seen_profile_keys: set[tuple[str, str, int, str]] = set()
    supported: list[tuple[int, dict]] = []
    for target in targets:
        identity = target.get("identity")
        if not isinstance(identity, dict):
            raise ValueError("target identity must be an object")
        version_code = identity.get("versionCode")
        if type(version_code) is not int or version_code <= 0:
            raise ValueError("target version code must be a positive integer")
        target_identity = identity
        if target_identity.get("packageName") != package_name or target_identity.get("abi") != abi:
            continue
        if target.get("verificationStatus") in SUPPORTED_STATUSES:
            raw_digest = identity.get("apkSha256")
            if not isinstance(raw_digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", raw_digest):
                raise ValueError("selected target has an invalid APK SHA-256")
            key = (package_name, abi, version_code, raw_digest.lower())
            if key in seen_profile_keys:
                raise ValueError("duplicate compatibility profile identity")
            seen_profile_keys.add(key)
            supported.append((version_code, target))

    supported.sort(key=lambda item: item[0])
    if supported and candidate_version_code < supported[-1][0]:
        raise ValueError("candidate version code is below the latest formally supported build")

    eligible = [(code, target) for code, target in supported if code <= candidate_version_code]
    capacity = 3 if any(code == candidate_version_code for code, _ in supported) else 2
    recent_codes = sorted({code for code, _ in eligible})[-capacity:]
    selected_codes = set(recent_codes)
    return [target for code, target in eligible if code in selected_codes]


def matrix_entries(targets: list[dict], app_id: Optional[str] = None) -> list[dict[str, object]]:
    entries = []
    for target in targets:
        identity = target["identity"]
        raw_digest = identity.get("apkSha256")
        digest = raw_digest.lower() if isinstance(raw_digest, str) else ""
        source_url = target.get("sourceUrl", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("selected target has an invalid APK SHA-256")
        policy = get_policy(app_id if app_id is not None else target.get("appId", "wechat"))
        if identity.get("packageName") != policy.package_name or identity.get("abi") not in policy.supported_abis:
            raise ValueError("selected target identity does not match the registered app policy")
        if not source_url.startswith(policy.official_apk_prefix) or not source_url.endswith(".apk"):
            raise ValueError("selected target source URL is outside the registered official APK directory")
        entries.append({
            "app_id": policy.app_id,
            "artifact_prefix": policy.artifact_prefix,
            "package_name": identity["packageName"],
            "abi": identity["abi"],
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
    parser.add_argument("--app-id", default="wechat")
    parser.add_argument("--package-name")
    parser.add_argument("--abi")
    parser.add_argument("--github-output", type=Path, required=True)
    arguments = parser.parse_args()

    targets = json.loads(arguments.targets.read_text(encoding="utf-8"))
    selected = select_regression_targets(targets, arguments.candidate_version_code,
                                         arguments.app_id, arguments.package_name, arguments.abi)
    matrix = matrix_entries(selected, arguments.app_id)
    append_github_output(arguments.github_output, {
        "matrix": json.dumps(matrix, separators=(",", ":")),
        "regression_versions": ",".join(str(entry["version_name"]) for entry in matrix),
    })
    print(f"Selected regression targets: {', '.join(str(row['version_name']) for row in matrix) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
