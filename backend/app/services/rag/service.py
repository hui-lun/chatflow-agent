import asyncio
import logging
from collections import OrderedDict
from raganything import RAGAnything

# Import the async factory function and the new state manager
from .factory import create_and_initialize_rag_for_user
from . import state_manager

class RAGService:
    """
    Manages the lifecycle of RAG instances and provides a high-level API
    for document processing and querying.

    Implements an LRU cache to manage memory usage by evicting instances
    for the least recently used users.
    """
    def __init__(self, max_cache_size: int = 100):
        """
        Initializes the service.
        :param max_cache_size: The maximum number of user RAG instances to keep in memory.
        """
        self._rag_instances = OrderedDict()
        self._instance_locks = {}
        self._max_cache_size = max_cache_size
        logging.info(f"RAGService initialized with an LRU cache size of {max_cache_size}.")

    async def _get_or_create_rag_instance(self, user_id: str) -> RAGAnything:
        """
        Retrieves a user-specific RAG instance from the cache or creates a new one.
        Uses an LRU policy to manage the cache size.
        """
        if user_id in self._rag_instances:
            self._rag_instances.move_to_end(user_id)
            return self._rag_instances[user_id]

        if user_id not in self._instance_locks:
            self._instance_locks[user_id] = asyncio.Lock()

        async with self._instance_locks[user_id]:
            if user_id in self._rag_instances:
                return self._rag_instances[user_id]

            logging.info(f"RAG instance for user '{user_id}' not in cache. Creating...")
            
            if len(self._rag_instances) >= self._max_cache_size:
                oldest_user_id, _ = self._rag_instances.popitem(last=False)
                self._instance_locks.pop(oldest_user_id, None)
                logging.info(f"Cache full. Evicted RAG instance for user '{oldest_user_id}'.")

            rag_system = await create_and_initialize_rag_for_user(user_id)
            
            self._rag_instances[user_id] = rag_system
            self._rag_instances.move_to_end(user_id)
            return rag_system

    async def process_document(self, user_id: str, file_path: str) -> bool:
        """
        Processes a document for a specific user, skipping if already processed.
        Returns True if processed, False if skipped.
        """
        state = await state_manager.load_state()
        if state_manager.is_file_processed(user_id, file_path, state):
            logging.info(f"Service: Document '{file_path}' already processed for user '{user_id}'. Skipping.")
            return False

        logging.info(f"Service: Processing document '{file_path}' for user '{user_id}'")
        try:
            rag_system = await self._get_or_create_rag_instance(user_id)
            await rag_system.process_document_complete(file_path=file_path, parse_method="auto")
            
            # Mark as processed and save state
            updated_state = state_manager.mark_file_as_processed(user_id, file_path, state)
            await state_manager.save_state(updated_state)
            
            logging.info(f"Service: Document '{file_path}' processed and marked as complete for user '{user_id}'")
            return True
        except Exception as e:
            logging.error(f"Service: Error processing document for user '{user_id}': {e}", exc_info=True)
            raise

    async def query(self, user_id: str, question: str) -> dict:
        """Performs a RAG query for a specific user."""
        logging.info(f"Service: Executing query for user '{user_id}': '{question[:50]}...'")
        try:
            rag_system = await self._get_or_create_rag_instance(user_id)
            
            # The logic to make the query user-specific is now correctly encapsulated
            # within the UserAwareLLM class in tenancy.py, so we pass the original question.
            response = await rag_system.aquery(question, mode="hybrid")
            
            answer = getattr(response, 'answer', str(response))
            retrieved_docs = getattr(response, 'context', [])
            
            def format_doc(doc):
                if hasattr(doc, 'to_dict'):
                    return doc.to_dict()
                return {"text": str(doc), "metadata": {}}

            formatted_docs = [format_doc(doc) for doc in retrieved_docs]
            logging.info(f"Service: Query for user '{user_id}' completed. Returning answer and {len(formatted_docs)} docs.")
            return {"response": answer, "retrieved_docs": formatted_docs}
        except Exception as e:
            logging.error(f"Service: Error during query for user '{user_id}': {e}", exc_info=True)
            raise


# Create a singleton instance of the RAGService
rag_service_instance = RAGService()