from src.dao import BaseDAO
from src.entities.probe.model import Probe


class ProbeDAO(BaseDAO[Probe]):
    model = Probe
