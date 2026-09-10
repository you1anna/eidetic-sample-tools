"""Independent, experimental Ableton Live control without a library database."""
from .client import LiveClient, LiveError
__version__ = '0.2.0'
__all__ = ['LiveClient', 'LiveError']
