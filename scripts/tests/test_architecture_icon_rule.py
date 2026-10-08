"""Architecture gate rule: web code must import icons from @/icons only."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_architecture", ROOT / "scripts" / "quality" / "check_architecture.py"
)
check_architecture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_architecture)

FEATURE_FILE = "apps/web/src/app/admin/agents/AgentCard.tsx"
BANNED = "Banned icon import; use @/icons only."


def banned_icon_lines(source: str, path: str = FEATURE_FILE) -> list[str]:
    findings = check_architecture.check_web(path, source.splitlines(), True)
    return [where for _, where, message in findings if message == BANNED]


class BannedIconImportTests(unittest.TestCase):
    def test_flags_real_world_import_forms(self) -> None:
        for source in (
            'import { Beaker } from "lucide-react";',
            "import { Beaker } from 'lucide-react'",
            'import { FaGithub } from "react-icons/fa";',
            'import { Gear } from "@phosphor-icons/react";',
            'export { Beaker } from "lucide-react";',
            'import "lucide-react";',
            'const Icons = await import("lucide-react");',
            "const icons = require('react-icons/md');",
        ):
            with self.subTest(source=source):
                self.assertEqual(banned_icon_lines(source), [f"{FEATURE_FILE}:1"])

    def test_flags_closing_line_of_multiline_import(self) -> None:
        source = 'import {\n  Beaker,\n  Check,\n} from "lucide-react";\n'

        self.assertEqual(banned_icon_lines(source), [f"{FEATURE_FILE}:4"])

    def test_ignores_allowed_or_non_import_references(self) -> None:
        for source in (
            'import { SvgCheck } from "@/icons";',
            'import { Beaker } from "lucide-react-native";',
            'const library = "lucide-react";',
            '// migrated away from "lucide-react"',
        ):
            with self.subTest(source=source):
                self.assertEqual(banned_icon_lines(source), [])

    def test_ignores_test_files(self) -> None:
        source = 'import { Beaker } from "lucide-react";'

        self.assertEqual(
            banned_icon_lines(source, "apps/web/src/app/AgentCard.test.tsx"), []
        )


if __name__ == "__main__":
    unittest.main()
