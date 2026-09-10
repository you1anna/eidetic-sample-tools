"""Shared package metadata for repository development and wheel checks."""

from __future__ import annotations


CORE_PACKAGES = (
    {"path": "library-tools", "import_name": "librarytools", "distribution": "librarytools"},
    {"path": "sample-tools", "import_name": "sampletools", "distribution": "sampletools"},
    {"path": "ableton-tools", "import_name": "abletontools", "distribution": "abletontools"},
)

LIVE_PACKAGE = {
    "path": "live-tools",
    "import_name": "eideticlive",
    "distribution": "eidetic-live-tools",
}

ALL_PACKAGES = (*CORE_PACKAGES, LIVE_PACKAGE)
