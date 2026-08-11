"""
Import every mapped class, so relationships can resolve.

SQLAlchemy resolves a relationship target by name against the registry
when mappers are configured, which is the first time anything is
queried. Every class in a relationship graph therefore has to have been
imported by then, and importing the service you happen to need is not
enough: VideoService reaches Video, whose `probes` relationship names a
class that nothing on that path imports. The query then fails with
"expression 'Probe' failed to locate a name".

Entry points import this module to get that guarantee in one place. Add
new models here.

This is deliberately a normal module rather than a package __init__:
as an __init__ it would run on every `src.entities.*` import and drag
the whole ORM - and with it the database engine - into modules that
only wanted an enum.
"""

from src.entities.probe.model import Probe  # noqa: F401
from src.entities.storage.model import Storage  # noqa: F401
from src.entities.video.model import Video  # noqa: F401
