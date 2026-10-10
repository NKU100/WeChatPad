"""Prepare an official APK for latest or registered runtime validation."""
import argparse
import copy
import importlib
import json
import shutil
from pathlib import Path

from scripts.ci.app_policy import get_policy, validate_targets
from scripts.ci.discover_latest_wechat import discover_from_html, fetch_official_page, validate_official_apk_url
from scripts.ci.fetch_latest_wechat_apk import download_candidate, remote_metadata
from scripts.ci.select_compatibility_window import SUPPORTED_STATUSES


def replay_report(targets, url, digest, app_id="wechat", selection_mode="latest"):
    policy = get_policy(app_id)
    validate_targets(targets, policy.app_id)
    validate_official_apk_url(url, policy.official_apk_prefix)
    matches = [row for row in targets if row['identity']['packageName'] == policy.package_name
               and row['identity']['abi'] in policy.supported_abis and row['sourceUrl'] == url
               and row['identity']['apkSha256'].lower() == digest.lower()]
    if len(matches) != 1:
        raise ValueError('Selected exact APK is not registered; run compatibility adaptation first')
    profile = copy.deepcopy(matches[0])
    if profile['verificationStatus'] not in SUPPORTED_STATUSES:
        raise ValueError('Selected profile is not runtime-verified; run compatibility adaptation first')
    profile['verificationStatus'] = 'static-verified'
    return {
        'appId': policy.app_id,
        'status': 'STATIC_VERIFIED_PENDING_RUNTIME',
        'identity': profile['identity'],
        'sourceUrl': url,
        'suggestedProfile': profile,
        'checkedVersions': [profile['identity']['versionName']],
        'replay': True,
        'selectionMode': selection_mode,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app-id', default='wechat')
    parser.add_argument('--targets', type=Path)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--mode', choices=('latest', 'registered'), default='latest')
    args = parser.parse_args()
    policy = get_policy(args.app_id)
    targets_path = args.targets or Path(policy.targets_path)
    targets = json.loads(targets_path.read_text())
    validate_targets(targets, policy.app_id)
    if args.mode == 'registered':
        matches = [row for row in targets if row['identity']['packageName'] == policy.package_name
                   and row['identity']['abi'] in policy.supported_abis
                   and row['verificationStatus'] in SUPPORTED_STATUSES]
        if not matches:
            raise ValueError('No runtime-verified registered APK is available for this application policy')
        highest_version_code = max(row['identity']['versionCode'] for row in matches)
        matches = [row for row in matches if row['identity']['versionCode'] == highest_version_code]
        if len(matches) != 1:
            raise ValueError('Highest runtime-verified registered APK is ambiguous across policy profiles')
        selected = matches[0]
        url = selected['sourceUrl']
        expected_sha256 = selected['identity']['apkSha256'].lower()
    else:
        strategy = importlib.import_module(policy.discovery_strategy)
        candidate = strategy.discover(policy)
        url = candidate.url
        validate_official_apk_url(url, policy.official_apk_prefix)
        matches = [row for row in targets if row['sourceUrl'] == url]
        if len(matches) != 1 or matches[0]['verificationStatus'] not in SUPPORTED_STATUSES:
            raise ValueError('Latest official APK is not runtime-verified; run compatibility adaptation first')
        selected = matches[0]
        expected_sha256 = selected['identity']['apkSha256'].lower()
    validate_official_apk_url(url, policy.official_apk_prefix)
    args.directory.mkdir(parents=True, exist_ok=True)
    apk, digest, _, _ = download_candidate(url, args.directory / 'cache', expected_sha256,
                                           remote_metadata(url, policy), policy)
    report = replay_report(targets, url, digest, policy.app_id, args.mode)
    shutil.copy2(apk, args.directory / f'{policy.app_id}.apk')
    (args.directory / 'candidate-report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
