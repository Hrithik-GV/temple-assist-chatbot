"""Base service interface and abstractions."""

from abc import ABC
import logging
from app.core.logging import get_logger


class BaseService(ABC):
    """Abstract base service class providing common logging and service utilities."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or get_logger(self.__class__.__name__)
