from pydantic import BaseModel, ConfigDict


class StorageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    server_group_id: int | None = None


class StorageCreate(BaseModel):
    name: str
    server_group_id: int | None = None


class StorageSlots(BaseModel):
    storage_id: int
    server_group_id: int
    free_slots: int
