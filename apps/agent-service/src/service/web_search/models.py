from abc import ABC, abstractmethod
from collections.abc import Sequence

from schemas.web_search import WebContent


class WebContentProvider(ABC):
    @abstractmethod
    def contents(self, urls: Sequence[str]) -> list[WebContent]:
        pass
