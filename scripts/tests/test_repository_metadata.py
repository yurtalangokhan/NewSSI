"""REPO-001 / REPO-002: the repository root must carry its own metadata.

Both rules are `required_files` checks against the repository root. REPO-002 was
counted in the static report's score block but never written into its `findings`
array, so it was missed on the first pass — these tests make both explicit.
"""

import tomllib
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class RepositoryMetadataTests(unittest.TestCase):
    def test_readme_exists_at_the_root(self) -> None:
        readme = REPOSITORY_ROOT / "README.md"
        self.assertTrue(readme.is_file(), "REPO-001: README.md missing from the repository root")
        self.assertTrue(readme.read_text(encoding="utf-8").strip(), "README.md is empty")

    def test_pyproject_exists_at_the_root(self) -> None:
        self.assertTrue(
            (REPOSITORY_ROOT / "pyproject.toml").is_file(),
            "REPO-002: pyproject.toml missing from the repository root",
        )

    def test_root_pyproject_declares_project_metadata(self) -> None:
        data = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data.get("project", {})

        for field in ("name", "version", "description", "requires-python"):
            self.assertTrue(project.get(field), f"root pyproject.toml is missing project.{field}")

    def test_root_pyproject_does_not_turn_the_repo_into_a_uv_workspace(self) -> None:
        """Each service pins and releases independently.

        Declaring `[tool.uv.workspace]` here would give them a shared lockfile
        and change dependency resolution for every one of them.
        """
        data = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertNotIn("workspace", data.get("tool", {}).get("uv", {}))

    def test_shared_ruff_standard_matches_the_packages(self) -> None:
        root = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package = tomllib.loads(
            (REPOSITORY_ROOT / "packages" / "error-contract" / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(root["tool"]["ruff"]["line-length"], package["tool"]["ruff"]["line-length"])
        self.assertEqual(
            root["tool"]["ruff"]["lint"]["select"], package["tool"]["ruff"]["lint"]["select"]
        )


if __name__ == "__main__":
    unittest.main()
