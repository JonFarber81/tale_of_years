"""Shim for legacy editable installs (`pip install -e .`).

All real project metadata lives in ``pyproject.toml``; this file exists only so
older setuptools/pip (which require a ``setup.py`` for editable mode) can install
the package in place. ``setup()`` with no args reads everything from pyproject.
"""

from setuptools import setup

setup()
