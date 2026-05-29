from pydantic import BaseModel


class StorageRead(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class StorageCreate(BaseModel):
    name: str
