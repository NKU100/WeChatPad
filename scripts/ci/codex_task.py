"""Persist adaptation records and publish only validated adaptation patches."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from scripts.ci.codex_adaptation import candidate_key, eligible_candidate
from scripts.ci.discover_latest_wechat import append_github_output


ADAPTATION_LABEL = "wechatpad-adaptation"


def trusted_attempt(issue):
    return (issue.get("user", {}).get("login") == "github-actions[bot]"
            and issue.get("user", {}).get("type") == "Bot"
            and "pull_request" not in issue)


def existing_attempt(issues, key):
    marker = f"<!-- wechatpad-adaptation:{key} -->"
    return next((issue for issue in issues if trusted_attempt(issue)
                 and any(label.get("name") == ADAPTATION_LABEL for label in issue.get("labels", []))
                 and marker in (issue.get("body") or "")), None)


def retry_allowed(issue, run):
    body = issue.get("body") or ""
    if 'Status: `NEEDS_HOOK_REVIEW`' in body:
        return True
    return ('Status: `ADAPTATION_RUNNING`' in body and run is not None
            and run.get("status") == "completed"
            and run.get("conclusion") in {"failure", "cancelled", "timed_out", "skipped", "startup_failure"})


def gh(*args):
    return subprocess.check_output(["gh", *args]).decode().strip()


def issue_body(report, status, run_url, pr_url=""):
    identity = report["identity"]
    lines = [f"<!-- wechatpad-adaptation:{candidate_key(report)} -->", f"Status: `{status}`", "",
             f"WeChat {identity['versionName']} ({identity['versionCode']})", f"APK SHA-256: `{identity['apkSha256']}`",
             f"Source: {report['sourceUrl']}", f"Run: {run_url}", "",
             "Model: `gpt-6-luna`; reasoning: `xhigh`; automatic retries disabled; manual retry available."]
    if pr_url:
        lines.extend(["", f"Adaptation PR: {pr_url}", "Hosted login-screen runtime evidence and merge are required before formal support."])
    else:
        lines.extend(["", "A failure or timeout is not retried automatically. Enable retry_adaptation in a manual run to retry."])
    return "\n".join(lines) + "\n"


def write_issue(repo, issue, body, directory):
    path = directory / "issue-body.md"
    path.write_text(body)
    return gh("issue", "edit", str(issue), "--repo", repo, "--body-file", str(path))


def claim(repo, report, targets, directory, run_url, retry=False):
    directory.mkdir(parents=True, exist_ok=True)
    if not eligible_candidate(report, targets):
        raise ValueError("Only verified, unknown candidate builds may start an adaptation")
    key = candidate_key(report)
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues?state=all&per_page=100"))
    issues = [issue for page in pages for issue in page]
    # Upgrade existing bot records so introducing the label does not repeat past attempts.
    marker = f"<!-- wechatpad-adaptation:{key} -->"
    previous = existing_attempt(issues, key)
    if previous is None:
        previous = next((issue for issue in issues if trusted_attempt(issue) and marker in (issue.get("body") or "")), None)
    gh("label", "create", ADAPTATION_LABEL, "--repo", repo, "--color", "1D76DB", "--description", "WeChat adaptation pipeline record", "--force")
    if previous:
        gh("issue", "edit", str(previous["number"]), "--repo", repo, "--add-label", ADAPTATION_LABEL)
        body_text = previous.get("body") or ""
        run = None
        run_match = re.search(r"^Run: https://github\.com/" + re.escape(repo) + r"/actions/runs/(\d+)$", body_text, re.MULTILINE)
        if retry and run_match and 'Status: `ADAPTATION_RUNNING`' in body_text:
            run = json.loads(gh("api", f"repos/{repo}/actions/runs/{run_match[1]}"))
        if retry and retry_allowed(previous, run) and "Adaptation PR:" not in body_text:
            if previous.get("state") == "closed":
                gh("issue", "reopen", str(previous["number"]), "--repo", repo)
            write_issue(repo, previous["number"], issue_body(report, "ADAPTATION_RUNNING", run_url), directory)
            append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"claimed": "true", "issue": str(previous["number"])})
            return
        append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"claimed": "false", "issue": str(previous["number"])})
        print(f"Reusing adaptation record #{previous['number']}; existing PRs keep their runtime verification path, without another model call.")
        return
    body = directory / "issue-body.md"
    body.write_text(issue_body(report, "ADAPTATION_RUNNING", run_url))
    url = gh("issue", "create", "--repo", repo, "--title", f"Adapt WeChat {report['identity']['versionName']} ({key})", "--body-file", str(body), "--label", ADAPTATION_LABEL)
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
                    "Hosted runtime smoke will check module injection, the Phone & Tablet entry and QR page before this PR is ready.\n\n"
                    f"[Adaptation run]({run_url}); tracks #{issue}.\n")
    url = gh("pr", "create", "--repo", repo, "--base", "main", "--head", branch, "--draft",
             "--title", f"feat: support WeChat {report['identity']['versionName']}", "--body-file", str(body))
    write_issue(repo, issue, issue_body(report, "WAITING_RUNTIME", run_url, url), directory)
    append_github_output(Path(os.environ["GITHUB_OUTPUT"]), {"pipeline_status": "WAITING_RUNTIME", "pr_url": url, "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout).decode().strip()})
    print(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["claim", "publish", "fail"])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--targets", type=Path)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--issue", type=int)
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    run_url = f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    if args.stage == "claim":
        claim(repo, json.loads(args.report.read_text()), json.loads(args.targets.read_text()), args.directory, run_url, retry=args.retry)
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
