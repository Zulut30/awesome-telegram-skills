"""Minimal child-process environment shared by the verification scripts.

Children get only what tools need to run on Windows, Linux and macOS, including
network proxies and CA bundles; application secrets such as BOT_TOKEN never pass.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping

_ALLOWED = {
    # Windows process and profile locations
    'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES',
    # POSIX home, temporary files and locale
    'HOME', 'TMPDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL', 'LC_CTYPE', 'XDG_CACHE_HOME',
    # network proxies and trust stores (corporate or sandbox proxies)
    'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE',
    'PIP_CERT', 'NODE_EXTRA_CA_CERTS', 'UV_NATIVE_TLS', 'UV_SYSTEM_CERTS',
    # browsers used by the Playwright checks
    'CHROME_PATH', 'PLAYWRIGHT_BROWSERS_PATH',
}


def minimal_environment(extra: Iterable[str] = (), source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy allowed variables (case-insensitive, so http_proxy also passes) plus `extra` names."""
    allowed = _ALLOWED | {name.upper() for name in extra}
    values = os.environ if source is None else source
    return {name: value for name, value in values.items() if name.upper() in allowed}


def planted_link(path: Path) -> bool:
    """A symlink or junction outside the OS layout; known links are refused.

    Root-owned aliases directly under / are trusted: on macOS /var, /tmp and /etc
    point to /private/..., so every temporary directory crosses one.
    """
    if not (path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())):
        return False
    try:
        return not (os.name != 'nt' and path.is_absolute() and path.parent == Path(path.anchor)
                    and path.lstat().st_uid == 0)
    except OSError:
        return True
