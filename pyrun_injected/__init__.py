from importlib.metadata import PackageNotFoundError, version

from .dllinject import pyRunner  # noqa

try:
    __version__ = version("pyrun_injected")
except PackageNotFoundError:
    pass
