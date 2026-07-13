"""LLM diff 추출·리뷰 파싱, 워크스페이스 diff 적용(실제 git), 프로바이더 URL 해석."""
import subprocess
from pathlib import Path

import pytest

from app.services import llm, workspace


def test_extract_diff_from_fence():
    reply = (
        "설명입니다.\n```diff\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n```\n끝."
    )
    diff = llm.extract_diff(reply)
    assert diff.startswith("--- a/x.py")
    assert "+b" in diff


def test_extract_diff_absent():
    assert llm.extract_diff("코드 변경이 필요 없습니다.") is None
    assert llm.extract_diff("```diff\n\n```") is None


def test_extract_diff_unfenced():
    reply = "diff --git a/y.py b/y.py\n--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-1\n+2\n"
    assert llm.extract_diff(reply).startswith("diff --git")


def test_resolve_internal_project_url():
    assert llm.resolve_base_url("project://llm-main") == "http://llm-main.apps.test"
    assert llm.resolve_base_url("https://api.anthropic.com/") == "https://api.anthropic.com"


def test_review_parsing(monkeypatch):
    monkeypatch.setattr(
        llm, "_post_chat",
        lambda url, headers, payload: {"choices": [{"message": {"content":
            '```json\n[{"severity": "high", "file": "a.py", "comment": "SQL 인젝션"}]\n```'
        }}]},
    )
    from app.models import LlmProvider, LlmProviderKind

    provider = LlmProvider(name="t", kind=LlmProviderKind.external,
                           base_url="https://x", model="m")
    findings = llm.review_diff(provider, "--- a/a.py\n+++ b/a.py\n")
    assert findings[0]["severity"] == "high"
    assert llm.max_severity(findings) == "high"
    assert llm.max_severity([]) == "none"


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "hello.py").write_text('print("hello")\n')
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        cwd=path, check=True,
    )


DIFF = """--- a/hello.py
+++ b/hello.py
@@ -1 +1 @@
-print("hello")
+print("hello, paas")
"""


def test_apply_diff_commits(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = workspace.apply_diff(repo, DIFF, "chat: greeting")
    assert len(sha) == 40
    assert (repo / "hello.py").read_text() == 'print("hello, paas")\n'
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo,
                         capture_output=True, text=True).stdout
    assert "chat: greeting" in log
    assert not (repo / ".paas-proposed.patch").exists()


def test_apply_bad_diff_raises(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    bad = DIFF.replace('-print("hello")', '-print("nope")')
    with pytest.raises(Exception):
        workspace.apply_diff(repo, bad, "x")


def test_context_files_guardrails(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "big.py").write_text("x" * 50_000)
    (repo / "bin.dat").write_text("data")
    files = workspace.read_context_files(repo, ["hello.py", "big.py", "bin.dat", "../escape"])
    assert list(files) == ["hello.py"]
