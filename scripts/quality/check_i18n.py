#!/usr/bin/env python3
import sys
from pathlib import Path

# Add packages/i18n-py/src to sys.path
root_dir = Path(__file__).resolve().parents[2]
i18n_src = root_dir / "packages" / "i18n-py" / "src"
if str(i18n_src) not in sys.path:
    sys.path.insert(0, str(i18n_src))

from i18n.checker import check_missing_translations


def main():
    success = check_missing_translations(root_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
