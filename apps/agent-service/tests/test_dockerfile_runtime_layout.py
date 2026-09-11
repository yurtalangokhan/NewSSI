from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def test_dockerfile_runtime_layout_can_import_app(tmp_path: Path) -> None:
    service_root = Path(__file__).resolve().parents[1]
    dockerfile = service_root / "docker" / "Dockerfile.service"
    dockerfile_text = dockerfile.read_text()

    for source, destination in re.findall(
        r"^COPY apps/agent-service/src/([^ ]+) ([^ ]+)$",
        dockerfile_text,
        flags=re.MULTILINE,
    ):
        source_path = service_root / "src" / source.rstrip("/")
        destination_path = tmp_path / destination.removeprefix("./").rstrip("/")

        if source_path.is_dir():
            shutil.copytree(source_path, destination_path)
        else:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)

    shutil.copytree(service_root / "locales", tmp_path / "locales")
    (tmp_path / "src").symlink_to(".")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    env["APP_ENV"] = "test"

    result = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
