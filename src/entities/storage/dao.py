from src.dao import BaseDAO
from src.entities.storage.model import Storage


class StorageDAO(BaseDAO[Storage]):
    model = Storage
