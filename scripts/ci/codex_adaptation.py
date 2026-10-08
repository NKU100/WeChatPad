"""Trusted controller for one bounded Codex adaptation and static validation."""

import argparse
import hashlib
import json
import os
import re
import signal
import tarfile
import tempfile
import subprocess
from pathlib import Path

from scripts.ci.discover_latest_wechat import append_github_output, validate_official_apk_url
from scripts.ci.select_compatibility_window import select_regression_targets
from scripts.ci.static_regression import check_apk, ensure_apk


MODEL = "gpt-6-luna"
REASONING = "xhigh"
ADAPTABLE_STATUSES = {"NEEDS_HOOK_REVIEW", "STATIC_VERIFIED_PENDING_RUNTIME"}


def candidate_key(report):
    identity = report["identity"]
    code, digest = identity["versionCode"], identity["apkSha256"]
    if type(code) is not int or code <= 0 or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Candidate version code or SHA-256 is invalid")
    return f"{code}-{digest}"


def eligible_candidate(report, targets):
    if report.get("status") not in ADAPTABLE_STATUSES:
        return False
    candidate_key(report)
    identity = report["identity"]
    validate_official_apk_url(report["sourceUrl"])
    trusted = [p for p in targets if p.get("verificationStatus") in {"runtime-verified-local", "runtime-verified-hosted"}]
    if not trusted:
        raise ValueError("No runtime-verified baseline is available")
    baseline = max(trusted, key=lambda p: p["identity"]["versionCode"])["identity"]
    if any(identity.get(k) != baseline[k] for k in ["packageName", "abi", "signerSha256"]):
        raise ValueError("Candidate identity does not match the trusted baseline")
    if any(p["identity"]["versionCode"] == identity["versionCode"] for p in targets):
        return False
    if identity["versionCode"] <= baseline["versionCode"]:
        raise ValueError("Candidate must be newer than the supported baseline")
    return True


def validate_profiles(before, after, report):
    if len(after) != len(before) + 1:
        raise ValueError("Adaptation must add exactly one profile and retain existing profiles")
    original = {p["identity"]["versionCode"]: p for p in before}
    updated = {p["identity"]["versionCode"]: p for p in after}
    if len(updated) != len(after) or any(updated.get(code) != profile for code, profile in original.items()):
        raise ValueError("Adaptation modified or removed an existing profile")
    candidate = updated.get(report["identity"]["versionCode"])
    if candidate is None or candidate["identity"] != report["identity"]:
        raise ValueError("Candidate profile identity must match the verified APK")
    if candidate.get("verificationStatus") != "static-verified":
        raise ValueError("Candidate must remain static-verified until runtime verification")
    if candidate.get("sourceUrl") != report["sourceUrl"]:
        raise ValueError("Candidate source must match the verified report")
    hooks = candidate.get("hooks", [])
    if len(hooks) != 2 or {h.get("id") for h in hooks} != {"tablet", "login"}:
        raise ValueError("Candidate requires exactly one tablet Hook and one login Hook")
    for hook in hooks:
        if not hook.get("stringAnchor") or not hook.get("expectedDescriptor"):
            raise ValueError("Candidate Hook anchors and descriptors must be explicit")


def validate_paths(paths):
    prefixes = ("app/src/main/kotlin/", "compat-core/src/main/kotlin/", "app/src/test/", "compat-core/src/test/")
    for path in paths:
        if path != "compatibility/targets.json" and not path.startswith(prefixes):
            raise ValueError(f"Agent edit is outside the allowed adaptation paths: {path}")


def run_bounded(command, cwd, env, log, timeout=None):
    with log.open("w") as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            result = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise TimeoutError(f"Command exceeded its {timeout}-second execution limit") from None
    if result:
        raise RuntimeError(f"Command failed with exit code {result}; raw output is retained only on the runner")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_existing_tests(worktree, existing_tests):
    for path, digest in existing_tests.items():
        if not (worktree / path).is_file() or sha256(worktree / path) != digest:
            raise ValueError("Existing regression tests must remain unchanged")


def git(cwd, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=cwd).decode().strip()


def prepare(repository, report_path, candidate_apk, directory):
    report = json.loads(report_path.read_text())
    before = json.loads((repository / "compatibility/targets.json").read_text())
    if not eligible_candidate(report, before):
        raise ValueError("Candidate is not eligible for a new adaptation attempt")
    if sha256(candidate_apk) != report["identity"]["apkSha256"]:
        raise ValueError("Candidate APK does not match the verified report")
    directory.mkdir(parents=True, exist_ok=True)
    worktree = directory / "checkout"
    base = git(repository, "rev-parse", "HEAD")
    # Export only build inputs; the model must not inherit repository history or reports.
    worktree.mkdir()
    paths = [".gitignore", "gradlew", "gradlew.bat", "gradle", "gradle.properties",
             "build.gradle.kts", "settings.gradle.kts", "app", "compat-core",
             "compat-checker", "compatibility/targets.json"]
    with tempfile.TemporaryFile() as archive:
        subprocess.run(["git", "archive", base, "--", *paths], cwd=repository, stdout=archive, check=True)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as source:
            members = source.getmembers()
            if any(not (member.isfile() or member.isdir())
                   or member.name.startswith("/") or ".." in Path(member.name).parts
                   for member in members):
                raise ValueError("Build input archive must contain only regular files and directories")
            source.extractall(worktree, members=members)
    subprocess.run(["git", "init", "--quiet", str(worktree)], check=True)
    subprocess.run(["git", "add", "."], cwd=worktree, check=True)
    subprocess.run(["git", "-c", "user.name=CI", "-c", "user.email=ci@localhost",
                    "commit", "--quiet", "-m", "Build inputs"], cwd=worktree, check=True)
    agent_base = git(worktree, "rev-parse", "HEAD")
    apk_dir = worktree / "work/apks"
    apk_dir.mkdir(parents=True)
    # Hard links avoid duplicating large, already verified APK files on the runner.
    os.link(candidate_apk, apk_dir / "candidate.apk")
    regression = select_regression_targets(before, report["identity"]["versionCode"])
    apks = [(report["identity"]["versionName"], "work/apks/candidate.apk")]
    for target in regression:
        identity = target["identity"]
        cached = ensure_apk(target, repository / ".cache/wechat-apks")
        destination = apk_dir / f"{identity['versionCode']}.apk"
        os.link(cached, destination)
        apks.append((identity["versionName"], str(destination.relative_to(worktree))))
    analysis = worktree / "work/analysis"
    analysis.mkdir(parents=True)
    (analysis / "candidate-report.json").write_text(json.dumps({
        "identity": report["identity"], "sourceUrl": report["sourceUrl"],
        "status": "UNKNOWN_BUILD"}, indent=2))
    existing_tests = {str(path.relative_to(worktree)): sha256(path)
                      for module in ["app", "compat-core"]
                      for path in (worktree / module / "src/test").rglob("*") if path.is_file()}
    state = {"worktree": str(worktree), "base": base, "agent_base": agent_base, "before": before, "report": report,
             "apks": apks, "existing_tests": existing_tests}
    (directory / "state.json").write_text(json.dumps(state, indent=2))


def run_model(directory, prompt_path, token_budget=200_000):
    from scripts.ci.codex_goal import run_model_goal
    run_model_goal(directory, prompt_path, token_budget)


def validate(directory):
    state = json.loads((directory / "state.json").read_text())
    worktree = Path(state["worktree"])
    if git(worktree, "rev-parse", "HEAD") != state.get("agent_base", state["base"]):
        raise ValueError("Agent must leave adaptation changes uncommitted")
    tracked = git(worktree, "diff", "--name-only", state.get("agent_base", state["base"])).splitlines()
    new_files = git(worktree, "ls-files", "--others", "--exclude-standard").splitlines()
    validate_paths(tracked + new_files)
    if any((worktree / path).is_symlink() for path in tracked + new_files):
        raise ValueError("Adaptation files must not be symbolic links")
    validate_existing_tests(worktree, state["existing_tests"])
    after = json.loads((worktree / "compatibility/targets.json").read_text())
    validate_profiles(state["before"], after, state["report"])
    candidate = state["report"]
    for version, apk in state["apks"]:
        expected = next(p for p in after if p["identity"]["versionName"] == version)["identity"]["apkSha256"]
        check_apk(worktree, Path("compatibility/targets.json"), worktree / apk, expected,
                  directory / f"check-{version}.log", offline=True)
    run_bounded(["./gradlew", "--offline", "--no-daemon", ":app:testDebugUnitTest", ":compat-core:test", ":compat-checker:test", ":app:assembleDebug"],
                worktree, dict(os.environ), directory / "build.log", timeout=600)
    for path in new_files:
        subprocess.run(["git", "add", "--", path], cwd=worktree, check=True)
    subprocess.run(["git", "diff", "--check", state.get("agent_base", state["base"])], cwd=worktree, check=True)
    with (directory / "adaptation.patch").open("w") as patch:
        subprocess.run(["git", "diff", "--binary", state.get("agent_base", state["base"])], cwd=worktree, stdout=patch, check=True)
    report = dict(candidate, status="STATIC_VERIFIED_PENDING_RUNTIME", blockers=[],
                  checkedVersions=[version for version, _ in state["apks"]],
                  suggestedProfile=next(p for p in after if p["identity"] == candidate["identity"]))
    # Findings describe the successful exact-profile checks, not the pre-adaptation failure.
    report["hooks"] = [{"hookId": h["id"], "status": "UNIQUE_MATCH", "stringAnchor": h["stringAnchor"],
                        "selectedDescriptor": h["expectedDescriptor"], "candidateDescriptors": [h["expectedDescriptor"]],
                        "message": "Verified against the adapted profile by the shared checker"}
                       for h in report["suggestedProfile"]["hooks"]]
    (directory / "candidate-report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["eligibility", "prepare", "model", "validate"])
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--prompt", type=Path)
    parser.add_argument("--goal-token-budget", type=int, default=200_000)
    args = parser.parse_args()
    if args.stage == "eligibility":
        report = json.loads(args.report.read_text())
        targets = json.loads((args.repository / "compatibility/targets.json").read_text())
        eligible = eligible_candidate(report, targets)
        append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"adaptation_eligible": str(eligible).lower()})
        print("Codex adaptation eligible:", eligible)
    elif args.stage == "prepare":
        prepare(args.repository.resolve(), args.report, args.apk.resolve(), args.directory.resolve())
    elif args.stage == "model":
        run_model(args.directory.resolve(), args.prompt, args.goal_token_budget)
    else:
        validate(args.directory.resolve())


if __name__ == "__main__":
    main()
