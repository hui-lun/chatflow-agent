import logging
from .search import search_and_summarize

logger = logging.getLogger(__name__)

def analyze_web_search(query: str) -> str:
    """
    Used for web analysis and external search, returns search results.
    """
    logger.info("[web_analyze] Executing web analysis/search")
    logger.debug(f"[web_analyze] Input query: {query}")
    
    if not isinstance(query, str) or not query.strip():
        logger.warning("[web_analyze] Empty or invalid query provided")
        return "Please provide a valid search query."
    
    try:
        logger.debug("[web_analyze] Starting web search and summarization")
        results = search_and_summarize(query)
        logger.info("[web_analyze] Successfully completed web search and summarization")
        return results
    except Exception as e:
        error_msg = f"Error occurred during web analysis: {e}"
        logger.error(f"[web_analyze] {error_msg}")
        return error_msg