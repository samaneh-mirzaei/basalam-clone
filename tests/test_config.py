import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_example_database_url_cannot_be_used():
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://basalam:replace-me@localhost:5432/basalam")
