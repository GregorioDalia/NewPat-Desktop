"""Compatibility entry point for the previously documented python -m nipat."""

from newpat import __version__

if __name__ == "__main__":
    from newpat.cli import main

    raise SystemExit(main())
