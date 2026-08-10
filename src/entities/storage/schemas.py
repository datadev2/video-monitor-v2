from pydantic import BaseModel, ConfigDict


class StorageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class StorageCreate(BaseModel):
    name: str
