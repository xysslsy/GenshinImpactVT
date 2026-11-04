"""Standalone portable uninstaller entry point (no Qt or .NET imports)."""
from genshinimpactvt.uninstaller import cli

if __name__ == '__main__':
    raise SystemExit(cli())
