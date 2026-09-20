#!/usr/bin/env python3
"""Check files or outgoing Git history without printing any matched values.

This guard catches private paths, non-example IPs, common credential formats,
and the owner's optional local denylist. It complements a general secret scanner;
it cannot prove that arbitrary prose or an unknown password contains no secrets.
"""
from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {".local", ".private", "private", "secrets", "data", "logs", ".venv", ".git"}
PRIVATE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".bundle", ".sqlite3", ".db", ".mp3", ".tar.gz", ".tgz", ".zip")
IPV4 = re.compile(rb"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
EXAMPLE_NETWORKS = tuple(ipaddress.ip_network(x) for x in (
    "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",
))
PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "provider credential": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})"),
    "credential in URL": re.compile(rb"https?://[^\s/:<>]+:[^\s/@<>]+@"),
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def private_path(name: str) -> bool:
    path = PurePosixPath(name)
    base = path.name
    return (bool(set(path.parts) & PRIVATE_PARTS)
            or (base == ".env" or base.startswith(".env.") or base.endswith(".env")) and not base.endswith(".example")
            or base.endswith(PRIVATE_SUFFIXES))


def local_denylist() -> list[bytes]:
    result = subprocess.run(["git", "config", "--get", "pocketreader.privateDir"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        return []
    path = Path(result.stdout.strip()) / "private-values.txt"
    # A configured but missing denylist must not silently disable owner protection.
    return [line for line in path.read_bytes().splitlines() if line.strip()]


def inspect(name: str, data: bytes, denylist: list[bytes]) -> list[str]:
    findings = []
    if private_path(name):
        findings.append("private file type or directory")
    for label, pattern in PATTERNS.items():
        if pattern.search(data):
            findings.append(label)
    for value in denylist:
        # Short original passwords can also be a substring of the project name.
        pattern = re.escape(value)
        if len(value) <= 8:
            pattern = rb"(?<![A-Za-z0-9_])" + pattern + rb"(?![A-Za-z0-9_])"
        if re.search(pattern, data):
            findings.append("known private value")
            break
    for match in IPV4.finditer(data):
        try:
            address = ipaddress.ip_address(match[0].decode())
        except ValueError:
            continue
        if address.is_loopback or address.is_unspecified or any(address in net for net in EXAMPLE_NETWORKS):
            continue
        findings.append("non-example IPv4 address")
        break
    # IPv6 URL hosts / bracketed literals. Bare arbitrary IPv6 prose is left to review.
    for match in re.finditer(rb"\[([0-9a-fA-F:]+)\]", data):
        try:
            address = ipaddress.ip_address(match[1].decode())
        except ValueError:
            continue
        if address.version == 6 and not (address.is_loopback or address.is_unspecified or address in ipaddress.ip_network("2001:db8::/32")):
            findings.append("non-example IPv6 address")
            break
    return findings


def blobs(refs: list[str]):
    seen = set()
    for ref in refs:
        for entry in git("rev-list", "--objects", ref).decode().splitlines():
            sha, _, name = entry.partition(" ")
            if sha in seen or not name:
                continue
            seen.add(sha)
            if git("cat-file", "-t", sha).strip() == b"blob":
                yield name, git("cat-file", "blob", sha)
        # Also inspect every historic path: a reused blob may have a new private name.
        for name in git("log", "--format=", "--name-only", ref).decode().splitlines():
            if name and private_path(name):
                yield name, b""
        yield "<commit messages>", git("log", "--format=%B", ref)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="Check complete Git index")
    group.add_argument("--history", action="store_true", help="Check all reachable history")
    group.add_argument("--pre-push", action="store_true", help="Read outgoing refs from hook stdin")
    args = parser.parse_args()
    denylist = local_denylist()
    if args.history:
        candidates = blobs(["--all"])
    elif args.pre_push:
        refs = [parts[1] for line in sys.stdin if len(parts := line.split()) == 4 and set(parts[1]) != {"0"}]
        candidates = blobs(refs)
    else:
        names = git("ls-files", "-z").decode().split("\0")
        if not args.staged:
            names += git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
        candidates = ((name, git("show", ":" + name) if args.staged else (ROOT / name).read_bytes())
                      for name in sorted(set(names)) if name and (args.staged or (ROOT / name).is_file()))
    issues = set()
    for name, data in candidates:
        for finding in inspect(name, data, denylist):
            issues.add((name, finding))
    for name, finding in sorted(issues):
        print(f"BLOCKED: {name}: {finding} (value withheld)", file=sys.stderr)
    if issues:
        return 1
    print("Public-content guard passed. Review changes and run a general secret scanner before publishing.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Public-content guard could not complete: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)
