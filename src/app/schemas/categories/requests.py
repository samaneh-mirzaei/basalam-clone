from pydantic import Field, model_validator

from app.api.http import StrictBody

class CategoryCreate(StrictBody):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    parent_id: int | None = Field(default=None, gt=0)


class CategoryPatch(StrictBody):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    parent_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def valid_patch(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set - {"parent_id"}):
            raise ValueError("Provide category fields; null is allowed only for parent_id.")
        return self
