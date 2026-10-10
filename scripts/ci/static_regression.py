"""Run the shared checker on exact, digest-verified official APKs."""
import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

from scripts.ci.app_policy import get_policy, validate_targets
from scripts.ci.discover_latest_wechat import validate_official_apk_url
from scripts.ci.fetch_latest_wechat_apk import download_candidate, file_sha256, remote_metadata

SUPPORTED = {'runtime-verified-local', 'runtime-verified-hosted'}


def registered_window(profiles, app_id='wechat'):
    policy = get_policy(app_id)
    validate_targets(profiles, policy.app_id)
    identities = [p.get('identity', {}) for p in profiles
                  if p.get('identity', {}).get('packageName') == policy.package_name]
    abis = {identity.get('abi') for identity in identities if identity.get('abi')}
    if len(abis) != 1:
        raise ValueError('Static regression requires one registered ABI for the app package')
    abi = next(iter(abis))
    supported = [p for p in profiles if p.get('verificationStatus') in SUPPORTED
                 and p.get('identity', {}).get('packageName') == policy.package_name
                 and p.get('identity', {}).get('abi') == abi]
    selected = sorted(supported, key=lambda p: (p['identity']['versionCode'], p['identity']['apkSha256']), reverse=True)[:3]
    if not selected:
        raise ValueError('Static regression requires at least one runtime-verified profile')
    return selected


def ensure_apk(profile, cache, app_id='wechat'):
    policy = get_policy(app_id)
    if profile.get('identity', {}).get('packageName') != policy.package_name:
        raise ValueError('Regression profile package does not match app policy')
    validate_official_apk_url(profile['sourceUrl'], policy.official_apk_prefix)
    digest = profile['identity']['apkSha256'].lower()
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise ValueError('Registered APK SHA-256 must contain 64 hexadecimal characters')
    path = cache / (digest + '.apk')
    if not path.is_file() or file_sha256(path) != digest:
        path, _, _, _ = download_candidate(profile['sourceUrl'], cache, digest,
                                           remote_metadata(profile['sourceUrl'], policy), policy)
    if file_sha256(path) != digest:
        raise ValueError('Regression APK hash does not match the registered profile')
    return path


def check_apk(repository, targets, apk, digest, log, offline=False, app_id='wechat'):
    apk = apk.resolve()
    if targets.is_file():
        validate_targets(json.loads(targets.read_text()), app_id)
    if file_sha256(apk) != digest.lower():
        raise ValueError('An APK changed after verification')
    arguments = shlex.join(['check', '--targets', str(targets), '--apk', str(apk), '--app-id', app_id])
    command = ['./gradlew', '--no-daemon']
    if offline:
        command.append('--offline')
    command.extend([':compat-checker:run', '--args=' + arguments])
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as output:
        subprocess.run(command, cwd=repository, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=300)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app-id', default='wechat')
    parser.add_argument('--targets', type=Path)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--reports', type=Path, default=Path('work/static-regression'))
    args = parser.parse_args()
    policy = get_policy(args.app_id)
    targets = args.targets or Path(policy.targets_path)
    cache = args.cache or Path('.cache') / f'{policy.app_id}-apks'
    profiles = registered_window(json.loads(targets.read_text()), policy.app_id)
    args.reports.mkdir(parents=True, exist_ok=True)
    summary = []
    failed = False
    for profile in profiles:
        identity = profile['identity']
        key = f"{policy.app_id}-{identity['packageName']}-{identity['abi']}-{identity['versionCode']}-{identity['apkSha256']}"
        try:
            apk = ensure_apk(profile, cache, policy.app_id)
            check_apk(Path.cwd(), targets, apk, identity['apkSha256'], args.reports / (key + '.log'), app_id=policy.app_id)
            summary.append({'appId': policy.app_id, 'identity': identity, 'status': 'PASSED'})
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            failed = True
            summary.append({'appId': policy.app_id, 'identity': identity, 'status': 'FAILED', 'error': str(error)})
        (args.reports / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    if failed:
        raise SystemExit('Static regression failed; see per-build logs and results.json')


if __name__ == '__main__':
    main()
