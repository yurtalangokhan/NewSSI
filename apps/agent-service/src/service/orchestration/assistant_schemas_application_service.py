"""AssistantSchemas application use cases."""

from core.observability.logger import get_logger
from schemas.assistants import AssistantSchemaResponse
from service.orchestration.assistant_schemas_service import AssistantSchemasService

logger = get_logger(__name__)


class AssistantSchemasApplicationService:
    """Framework-free application use cases for this JSON surface."""

    def __init__(self, schemas_service: AssistantSchemasService):
        self.schemas_service = schemas_service

    async def get_assistant_schemas(self, assistant_id: str) -> AssistantSchemaResponse:
        """
        Get schemas for an assistant's configuration.
        Returns graph-specific config schemas with x_oap_ui_config metadata
        for Open Agent Platform.
        """
        service = self.schemas_service
        return await service.get_assistant_schemas(assistant_id)
