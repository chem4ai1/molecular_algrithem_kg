#!/usr/bin/env python3
"""通过 GitHub REST API 上传仓库（不依赖 github.com:443，只需 api.github.com）。

用法：
    GITHUB_TOKEN=ghp_xxx python scripts/push_via_api.py
    # 或
    python scripts/push_via_api.py ghp_xxx

为什么需要它：本机实测 github.com:443 不可达（git push 超时），
但 api.github.com 可正常访问，因此走 Git Data API：
    blobs → tree → commit → 更新 refs/heads/main

Token 要求：classic PAT 需 `repo` 权限；fine-grained 需
Contents: Read and write + Metadata: Read。
"""
from __future__ import annotations
import base64, json, os, subprocess, sys, time
import urllib.error, urllib.request
from pathlib import Path

OWNER = os.environ.get("GH_OWNER", "chem4ai1")
REPO = os.environ.get("GH_REPO", "molecular_algrithem_kg")
API = "https://api.github.com"
BRANCH = "main"
MSG = ("feat: 论文知识抽取 → 语义层 → 应用层 → 论文复现全链路\n\n"
       "- 语义层 6001 节点 / 7460 断言（6 类 9 关系）\n"
       "- 应用层任务化：复现 8300 / 生成 8853 节点\n"
       "- 复现四环节：方法锁定 / 代码生成 / 复现执行 / 主张锚定\n"
       "- 层次化 rubric 树 + networkx 图适配（MultiDiGraph/GraphML）\n"
       "- 前端：/data /relations /repro /pipeline")


def req(method: str, path: str, token: str, body=None, retries: int = 4):
    url = path if path.startswith("http") else API + path
    data = None if body is None else json.dumps(body).encode()
    for i in range(retries):
        r = urllib.request.Request(url, data=data, method=method)
        r.add_header("Authorization", "Bearer " + token)
        r.add_header("Accept", "application/vnd.github+json")
        r.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode(errors="replace")
            if e.code in (403, 429) and i < retries - 1:
                time.sleep(2 ** i * 2)
                continue
            return e.code, {"error": detail}
        except Exception as e:  # noqa: BLE001
            if i < retries - 1:
                time.sleep(2 ** i)
                continue
            return 0, {"error": f"{type(e).__name__}: {e}"}
    return 0, {"error": "retries_exhausted"}


def main() -> int:
    token = (sys.argv[1] if len(sys.argv) > 1 else
             os.environ.get("GITHUB_TOKEN", "")).strip()
    if not token:
        print("缺少 token：GITHUB_TOKEN=... 或作为第一个参数传入")
        return 2
    st, me = req("GET", "/user", token)
    if st != 200:
        print(f"token 校验失败：HTTP {st} {me.get('error', '')[:120]}")
        return 2
    print("认证用户:", me.get("login"))

    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(["git", "ls-files"], cwd=root,
                                    text=True).splitlines()
    files = [f for f in files if (root / f).is_file()]
    print(f"待上传文件 {len(files)} 个")

    blobs = []
    for i, f in enumerate(files, 1):
        raw = (root / f).read_bytes()
        st, d = req("POST", f"/repos/{OWNER}/{REPO}/git/blobs", token,
                    {"content": base64.b64encode(raw).decode(),
                     "encoding": "base64"})
        if st not in (200, 201):
            print(f"  blob 失败 {f}: {st} {d.get('error', '')[:120]}")
            return 1
        mode = "120000" if (root / f).is_symlink() else "100644"
        blobs.append({"path": f, "mode": mode, "type": "blob",
                      "sha": d["sha"]})
        if i % 50 == 0 or i == len(files):
            print(f"  blobs {i}/{len(files)}")

    st, d = req("POST", f"/repos/{OWNER}/{REPO}/git/trees", token,
                {"tree": blobs})
    if st not in (200, 201):
        print("tree 创建失败:", st, d.get("error", "")[:200])
        return 1
    tree_sha = d["sha"]

    st, ref = req("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}",
                  token)
    parents = [ref["object"]["sha"]] if st == 200 else []
    st, c = req("POST", f"/repos/{OWNER}/{REPO}/git/commits", token,
                {"message": MSG, "tree": tree_sha, "parents": parents})
    if st not in (200, 201):
        print("commit 失败:", st, c.get("error", "")[:200])
        return 1
    commit_sha = c["sha"]

    st, _ = req("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}",
                token, {"sha": commit_sha, "force": False})
    if st not in (200, 201):
        st2, _ = req("POST", f"/repos/{OWNER}/{REPO}/git/refs", token,
                     {"ref": f"refs/heads/{BRANCH}", "sha": commit_sha})
        if st2 not in (200, 201):
            print("更新 ref 失败:", st, st2)
            return 1
    print("完成 · commit:", commit_sha)
    print("仓库: https://github.com/" + OWNER + "/" + REPO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
