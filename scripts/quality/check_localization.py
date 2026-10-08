#!/usr/bin/env python3
import sys
from pathlib import Path

# Make the localization package importable without installing it
root_dir = Path(__file__).resolve().parents[2]
localization_src = root_dir / "packages" / "localization" / "src"
if str(localization_src) not in sys.path:
    sys.path.insert(0, str(localization_src))

from localization.checker import check_missing_translations


def main():
    success = check_missing_translations(root_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
