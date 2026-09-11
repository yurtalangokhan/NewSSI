from pathlib import Path

import yaml


def test_airbyte_worker_and_webapp_have_required_image_configuration():
    path = Path(__file__).resolve().parents[2] / "configs/docker-compose-services.yml"
    config = yaml.safe_load(path.read_text())
    services = config["services"]
    worker = services["airbyte-worker"]["environment"]
    assert worker["MICRONAUT_ENVIRONMENTS"] == "control-plane"
    assert worker["WORKSPACE_DOCKER_MOUNT"] == config["volumes"]["airbyte-workspace"]["name"]
    assert worker["LOCAL_DOCKER_MOUNT"] == "${AIRBYTE_LOCAL_ROOT}"
    assert services["airbyte-webapp"]["environment"]["KEYCLOAK_INTERNAL_HOST"] == "localhost"
