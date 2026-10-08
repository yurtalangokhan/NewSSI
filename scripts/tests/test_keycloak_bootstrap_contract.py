"""Contracts of scripts/bootstrap_keycloak.sh that a rehearsal against Keycloak found broken.

The script is bash + jq; the jq programs it sends to the Admin API are kept in shell variables
so that they can be run here with jq, when jq is installed, against representative inputs.
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT = REPOSITORY_ROOT / "scripts" / "bootstrap_keycloak.sh"


def jq_program(script: str, variable: str) -> str:
    match = re.search(rf"(?ms)^{variable}='(?P<program>[^']*)'$", script)
    assert match is not None, f"{variable} is not defined as a single-quoted shell variable"
    return match.group("program")


class KeycloakBootstrapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
        cls.jq = shutil.which("jq")

    def run_jq(self, program: str, current: dict, **args: str) -> dict:
        if self.jq is None:
            self.skipTest("needs jq")
        command = [self.jq, "-n", "--argjson", "current", json.dumps(current)]
        for name, value in args.items():
            command += ["--arg", name, value]
        command.append(program)
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_existing_backend_client_is_updated_from_its_current_representation(self) -> None:
        """A PUT without authorizationServicesEnabled disables authorization services
        (Keycloak 26.1 and 26.8) and deletes every resource and policy of the client."""
        section = self.script[self.script.index("# 4. Backend service clients") :]
        section = section[: section.index("# 5. Realm roles")]
        self.assertRegex(
            section,
            r'current="\$\(curl -fsS "\$BASE/admin/realms/\$KEYCLOAK_REALM/clients/\$UUID"',
            "the update does not start from the client's current representation",
        )
        self.assertIn('--argjson current "$current"', section)
        self.assertIn('"$BACKEND_CLIENT_UPDATE"', section)

        current = {
            "id": "7b3f",
            "clientId": "user-service",
            "enabled": False,
            "authorizationServicesEnabled": True,
            "serviceAccountsEnabled": True,
            "publicClient": False,
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": True,
            "attributes": {"post.logout.redirect.uris": "+"},
            "redirectUris": ["http://localhost/*"],
            "protocolMappers": [{"name": "agentic-gateway-audience"}],
        }
        updated = self.run_jq(
            jq_program(self.script, "BACKEND_CLIENT_UPDATE"), current, clientId="user-service"
        )

        self.assertEqual(
            {
                **current,
                "enabled": True,
                "protocol": "openid-connect",
                "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False,
            },
            updated,
        )

    def test_test_user_gets_a_first_and_a_last_name(self) -> None:
        """Without them the realm's user profile is incomplete and a password login
        answers 400 "Account is not fully set up"."""
        section = self.script[self.script.index("# 7. Test user") :]
        section = section[: section.index("# 8. Default admin user")]
        self.assertEqual(
            2,
            section.count('"$TEST_USER_UPDATE"'),
            "both the creation and the update of an existing user must complete the profile",
        )
        self.assertRegex(
            section, r'http_code PUT "\$BASE/admin/realms/\$KEYCLOAK_REALM/users/\$USER_UUID"'
        )
        program = jq_program(self.script, "TEST_USER_UPDATE")

        created = self.run_jq(
            program,
            {"username": "test-user", "email": "t@example.com", "enabled": True, "emailVerified": True},
        )
        self.assertEqual(("Test", "User"), (created["firstName"], created["lastName"]))
        self.assertEqual("test-user", created["username"])

        partial = self.run_jq(program, {"id": "1", "firstName": "Ayşe", "lastName": ""})
        self.assertEqual(("Ayşe", "User"), (partial["firstName"], partial["lastName"]))

        complete = {"id": "1", "firstName": "Ayşe", "lastName": "Yılmaz", "attributes": {"a": ["1"]}}
        self.assertEqual(complete, self.run_jq(program, complete))


if __name__ == "__main__":
    unittest.main()
