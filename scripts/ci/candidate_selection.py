"""Prepare the latest official APK for registered runtime validation."""
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


def replay_report(targets, url, digest, app_id="wechat"):
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
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app-id', default='wechat')
    parser.add_argument('--targets', type=Path)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    policy = get_policy(args.app_id)
    targets_path = args.targets or Path(policy.targets_path)
    targets = json.loads(targets_path.read_text())
    validate_targets(targets, policy.app_id)
    strategy = importlib.import_module(policy.discovery_strategy)
    candidate = strategy.discover(policy)
    validate_official_apk_url(candidate.url, policy.official_apk_prefix)
    matches = [row for row in targets if row['sourceUrl'] == candidate.url]
    if len(matches) != 1 or matches[0]['verificationStatus'] not in SUPPORTED_STATUSES:
        raise ValueError('Latest official APK is not runtime-verified; run compatibility adaptation first')
    args.directory.mkdir(parents=True, exist_ok=True)
    apk, digest, _, _ = download_candidate(candidate.url, args.directory / 'cache',
                                           matches[0]['identity']['apkSha256'].lower(),
                                           remote_metadata(candidate.url, policy), policy)
    report = replay_report(targets, candidate.url, digest, policy.app_id)
    shutil.copy2(apk, args.directory / f'{policy.app_id}.apk')
    (args.directory / 'candidate-report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
