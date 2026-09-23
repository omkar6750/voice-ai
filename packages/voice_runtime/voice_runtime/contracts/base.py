"""Shared strict configuration foundation."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
