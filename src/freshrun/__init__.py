"""Fresh interactive IPython subprocesses."""

from .freshrun import FreshRunMagics
from .freshimport import FreshImportMagics
from .tools import InjectPullMagics

def load_ipython_extension(ipython):
    """Load the %freshrun IPython extension."""
    ipython.register_magics(FreshRunMagics)
    ipython.register_magics(FreshImportMagics)
    ipython.register_magics(InjectPullMagics)

__all__ = [
    "FreshRunMagics",
    "FreshImportMagics",
    "InjectPullMagics",
    "load_ipython_extension",
]
