from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class AbstractVectorStore(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        pass

class AbstractLLMProvider(ABC):
    @abstractmethod
    def generate_grounded_answer(
        self, query: str, context_chunks: List[Dict[str, Any]], language: str = "en",
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        pass

    def condense_query(self, query: str, conversation_history: List[Dict[str, str]] = None) -> str:
        return query

class AbstractCRMProvider(ABC):
    @abstractmethod
    def create_lead(
        self, phone_number: str, name: Optional[str], concern: Optional[str], channel: str
    ) -> Dict[str, Any]:
        pass

class AbstractOrderProvider(ABC):
    @abstractmethod
    def get_order_status(self, query: str) -> Dict[str, Any]:
        pass
