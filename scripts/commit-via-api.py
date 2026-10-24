#!/usr/bin/env python3
"""把本地打包工程提交到 GitHub（Contents/Git Data API），不依赖 git。

用法:
  GH_TOKEN=xxx python scripts/commit-via-api.py \
      --repo dreamalloc/postgres --branch ci/pg13-rpm \
      --base REL_13_23 --message "ci(rpm): ..."
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"

FILES = [
    ".github/workflows/build-pg13-kylin-arm64.yml",
    ".github/workflows/build-pg13-openeuler2403-x86_64.yml",
    "packaging/rpm/postgresql13.spec",
    "scripts/prepare-build-env.sh",
    "scripts/prepare-build-env-oe.sh",
    "scripts/build-rpm.sh",
    "scripts/verify-rpm.sh",
    "scripts/commit-via-api.py",
]

EXECUTABLE = {p for p in FILES if p.endswith(".sh") or p.endswith(".py")}


def call(method, path, payload=None, token=""):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print(f"!! {method} {path} -> {e.code}: {e.read().decode()[:400]}")
        raise


def resolve_commit(repo, ref, token):
    """把 tag / 分支 / commit 解析成 commit sha。"""
    try:
        obj = call("GET", f"/repos/{repo}/git/ref/tags/{ref}", token=token)["object"]
        if obj["type"] == "tag":
            obj = call("GET", f"/repos/{repo}/git/tags/{obj['sha']}", token=token)["object"]
        return obj["sha"]
    except urllib.error.HTTPError:
        pass
    return call("GET", f"/repos/{repo}/git/ref/heads/{ref}", token=token)["object"]["sha"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", default="master", help="新分支的起点（tag/分支/commit）")
    ap.add_argument("--message", required=True)
    args = ap.parse_args()

    token = os.environ.get("GH_TOKEN") or ""
    if not token:
        sys.exit("缺少 GH_TOKEN")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    base_sha = resolve_commit(args.repo, args.base, token)
    print(f"    base {args.base} -> {base_sha[:9]}")

    # 分支是否存在
    parent = None
    try:
        parent = call("GET", f"/repos/{args.repo}/git/ref/heads/{args.branch}", token=token)["object"]["sha"]
        print(f"    分支已存在，基于 {parent[:9]}")
    except urllib.error.HTTPError:
        parent = base_sha
        call("POST", f"/repos/{args.repo}/git/refs",
             {"ref": f"refs/heads/{args.branch}", "sha": base_sha}, token=token)
        print("    已创建分支")

    entries = []
    for rel in FILES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            print(f"    (跳过，本地不存在: {rel})")
            continue
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        sha = call("POST", f"/repos/{args.repo}/git/blobs",
                   {"content": content, "encoding": "base64"}, token=token)["sha"]
        entries.append({
            "path": rel,
            "mode": "100755" if rel in EXECUTABLE else "100644",
            "type": "blob",
            "sha": sha,
        })
        print(f"    + {rel}")

    base_tree = call("GET", f"/repos/{args.repo}/git/commits/{parent}", token=token)["tree"]["sha"]
    tree = call("POST", f"/repos/{args.repo}/git/trees",
                {"base_tree": base_tree, "tree": entries}, token=token)["sha"]
    commit = call("POST", f"/repos/{args.repo}/git/commits",
                  {"message": args.message, "tree": tree, "parents": [parent]}, token=token)
    call("PATCH", f"/repos/{args.repo}/git/refs/heads/{args.branch}",
         {"sha": commit["sha"], "force": True}, token=token)
    print(f"\n完成：https://github.com/{args.repo}/commit/{commit['sha']}")


if __name__ == "__main__":
    main()
