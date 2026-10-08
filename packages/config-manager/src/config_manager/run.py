"""Launch a process with the shared environment, without a shell or interpolation."""

import subprocess
import sys

from .manager import load_environment


def main(argv: list[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        print("Usage: python -m config_manager.run -- COMMAND [ARG ...]", file=sys.stderr)
        return 2
    try:
        load_environment()
        return subprocess.run(command, check=False).returncode
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
