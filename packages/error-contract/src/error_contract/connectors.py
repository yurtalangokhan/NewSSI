"""Application-owned errors for bounded connector reads."""

from .exceptions import ApplicationError

_CATEGORY_STATUS = {
    "authorization": 403,
    "configuration": 500,
    "validation": 400,
    "connection": 503,
    "timeout": 504,
    "authentication": 502,
    "unsupported": 400,
    "response": 502,
}


class ConnectorAccessError(ApplicationError):
    """Safe connector failure carrying a machine-readable category."""

    category = "connection"
    code = "connector.connection"
    message_key = "errors.connector.connection"

    def __init__(self, message: str = "Connector operation failed.", category: str | None = None):
        self.category = category or self.category
        super().__init__(
            status_code=_CATEGORY_STATUS.get(self.category, 500),
            code=f"connector.{self.category}",
            message=message,
            message_key=f"errors.connector.{self.category}",
            message_params={"message": message},
        )


class ConnectorSqlError(ConnectorAccessError):
    """Safe SQL adapter error."""


class ConnectorSqlConfigurationError(ConnectorSqlError):
    category = "configuration"
    code = "connector.configuration"
    message_key = "errors.connector.configuration"


class ConnectorSqlValidationError(ConnectorSqlError):
    category = "validation"
    code = "connector.validation"
    message_key = "errors.connector.validation"


class ConnectorKafkaError(ConnectorAccessError):
    """Safe Kafka adapter error."""


class ConnectorKafkaConfigurationError(ConnectorKafkaError):
    category = "configuration"
    code = "connector.configuration"
    message_key = "errors.connector.configuration"


class ConnectorKafkaValidationError(ConnectorKafkaError):
    category = "validation"
    code = "connector.validation"
    message_key = "errors.connector.validation"


class MicrosoftConnectorError(ConnectorAccessError):
    """Safe Microsoft Graph adapter error."""


class MicrosoftConfigurationError(MicrosoftConnectorError):
    category = "configuration"
    code = "connector.configuration"
    message_key = "errors.connector.configuration"


class MicrosoftValidationError(MicrosoftConnectorError):
    category = "validation"
    code = "connector.validation"
    message_key = "errors.connector.validation"


class MicrosoftAuthenticationError(MicrosoftConnectorError):
    category = "authentication"
    code = "connector.authentication"
    message_key = "errors.connector.authentication"
