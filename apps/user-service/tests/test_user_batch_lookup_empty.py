import pytest
from pydantic import ValidationError

from src.schema.users import InternalUserBatchRequest


def test_batch_request_rejects_empty_user_ids() -> None:
    with pytest.raises(ValidationError):
        InternalUserBatchRequest(user_ids=[])
