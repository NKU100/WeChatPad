"""Persist one-attempt records and publish only validated adaptation patches."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from scripts.ci.codex_adaptation import candidate_key, eligible_candidate
from scripts.ci.discover_latest_wechat import append_github_output


def existing_attempt(issues, key):
    marker = f"<!-- wechatpad-adaptation:{key} -->"
    return next((issue for issue in issues if marker in (issue.get("body") or "")), None)


def gh(*args):
    return subprocess.check_output(["gh", *args]).decode().strip()


def issue_body(report, status, run_url, pr_url=""):
    identity = report["identity"]
    lines = [f"<!-- wechatpad-adaptation:{candidate_key(report)} -->", f"Status: `{status}`", "",
             f"WeChat {identity['versionName']} ({identity['versionCode']})", f"APK SHA-256: `{identity['apkSha256']}`",
             f"Source: {report['sourceUrl']}", f"Run: {run_url}", "",
             "Model: `gpt-6-luna`; reasoning: `xhigh`; one adaptation attempt."]
    if pr_url:
        lines.extend(["", f"Draft PR: {pr_url}", "Local login-screen runtime smoke is required before formal support."])
    else:
        lines.extend(["", "This build is claimed once. A failure or timeout is not retried automatically."])
    return "\n".join(lines) + "\n"


def write_issue(repo, issue, body, directory):
    path = directory / "issue-body.md"
    path.write_text(body)
    return gh("issue", "edit", str(issue), "--repo", repo, "--body-file", str(path))


def claim(repo, report, targets, directory, run_url):
    directory.mkdir(parents=True, exist_ok=True)
    if not eligible_candidate(report, targets):
        raise ValueError("Only verified, unknown candidate builds may start an adaptation")
    key = candidate_key(report)
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues?state=all&per_page=100"))
    previous = existing_attempt([issue for page in pages for issue in page], key)
    if previous:
        append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"claimed": "false", "issue": str(previous["number"])})
        print(f"Skipping prior adaptation attempt #{previous['number']}")
        return
    body = directory / "issue-body.md"
    body.write_text(issue_body(report, "ADAPTATION_RUNNING", run_url))
    url = gh("issue", "create", "--repo", repo, "--title", f"Adapt WeChat {report['identity']['versionName']} ({key})", "--body-file", str(body))
    number = int(url.rsplit("/", 1)[1])
    append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"claimed": "true", "issue": str(number)})
    print(f"Claimed one adaptation attempt: #{number}")


def publish(repo, directory, issue, run_url):
    state = json.loads((directory / "state.json").read_text())
    report = json.loads((directory / "candidate-report.json").read_text())
    if report["status"] != "STATIC_VERIFIED_PENDING_RUNTIME":
        raise ValueError("Draft PR requires successful candidate and regression checks")
    key = candidate_key(report)
    branch = "adapt/wechat-" + key
    checkout = Path(os.environ["GITHUB_WORKSPACE"])
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout).decode().strip()
    current_main = gh("api", f"repos/{repo}/git/ref/heads/main", "--jq", ".object.sha")
    if head != state["base"] or current_main != head:
        raise ValueError("Main changed during adaptation; manual reconciliation is required")
    subprocess.run(["git", "switch", "-c", branch], cwd=checkout, check=True)
    subprocess.run(["git", "apply", "--index", str(directory / "adaptation.patch")], cwd=checkout, check=True)
    subprocess.run(["git", "config", "user.name", "NKU100"], cwd=checkout, check=True)
    subprocess.run(["git", "config", "user.email", "21164383+NKU100@users.noreply.github.com"], cwd=checkout, check=True)
    subprocess.run(["git", "commit", "-m", f"feat: support WeChat {report['identity']['versionName']}"], cwd=checkout, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + branch], cwd=checkout, check=True)
    body = directory / "pr-body.md"
    versions = ", ".join(report["checkedVersions"])
    body.write_text(f"Adds the verified WeChat {report['identity']['versionName']} build as a static-verified profile.\n\n"
                    f"The shared checker passed for: {versions}. Shared-core and module tests and the debug APK build passed.\n\n"
                    "Local runtime login-screen smoke is still required. Update the profile to runtime-verified-local only after recording that result.\n\n"
                    f"[Adaptation run]({run_url}); tracks #{issue}.\n")
    url = gh("pr", "create", "--repo", repo, "--base", "main", "--head", branch, "--draft",
             "--title", f"feat: support WeChat {report['identity']['versionName']}", "--body-file", str(body))
    write_issue(repo, issue, issue_body(report, "WAITING_LOCAL_RUNTIME", run_url, url), directory)
    append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"pipeline_status": "WAITING_LOCAL_RUNTIME", "pr_url": url})
    print(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["claim", "publish", "fail"])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--targets", type=Path)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--issue", type=int)
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    run_url = f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    if args.stage == "claim":
        claim(repo, json.loads(args.report.read_text()), json.loads(args.targets.read_text()), args.directory, run_url)
    elif args.stage == "publish":
        publish(repo, args.directory, args.issue, run_url)
    else:
        report = json.loads(args.report.read_text())
        report.update(status="NEEDS_HOOK_REVIEW", suggestedProfile=None,
                      blockers=["Codex adaptation or static validation failed. See the run steps; no automatic retry is scheduled."])
        (args.directory / "candidate-report.json").write_text(json.dumps(report, indent=2) + "\n")
        write_issue(repo, args.issue, issue_body(report, "NEEDS_HOOK_REVIEW", run_url), args.directory)
        append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"pipeline_status": "NEEDS_HOOK_REVIEW"})


if __name__ == "__main__":
    main()
