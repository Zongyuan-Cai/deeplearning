from abc import ABC, abstractmethod


class BaseSelector(ABC):
    @abstractmethod
    def select(self, file_path: str):
        raise NotImplementedError
