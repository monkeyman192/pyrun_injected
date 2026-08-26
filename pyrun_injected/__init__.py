from importlib.metadata import PackageNotFoundError, version
from logging import NullHandler, getLogger

from .dllinject import pyRunner  # noqa

try:
    __version__ = version("pyrun_injected")
except PackageNotFoundError:
    pass


logger = getLogger(__name__)
logger.addHandler(NullHandler())
