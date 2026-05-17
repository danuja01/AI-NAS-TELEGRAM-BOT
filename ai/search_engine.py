"""
Internet search integration using Serper or Tavily APIs.
"""

import logging
import aiohttp
from typing import List, Dict, Any, Optional

import config

logger = logging.getLogger(__name__)


async def search_web(query: str, num_results: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    Search the web using available search API.
    
    Args:
        query: Search query
        num_results: Number of results to return
    
    Returns:
        List of search results or None if unavailable
    """
    # Try Serper first
    if config.SERPER_API_KEY:
        results = await _search_serper(query, num_results)
        if results:
            return results
    
    # Try Tavily as fallback
    if config.TAVILY_API_KEY:
        results = await _search_tavily(query, num_results)
        if results:
            return results
    
    logger.warning("No search API available (Serper or Tavily)")
    return None


async def _search_serper(query: str, num_results: int) -> Optional[List[Dict[str, Any]]]:
    """Search using Serper API."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'X-API-KEY': config.SERPER_API_KEY,
                'Content-Type': 'application/json'
            }
            
            payload = {
                'q': query,
                'num': num_results
            }
            
            async with session.post(
                'https://google.serper.dev/search',
                json=payload,
                headers=headers,
                timeout=10
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    for item in data.get('organic', [])[:num_results]:
                        results.append({
                            'title': item.get('title', ''),
                            'snippet': item.get('snippet', ''),
                            'link': item.get('link', '')
                        })
                    
                    return results
                else:
                    logger.warning(f"Serper returned status {response.status}")
                    return None
    
    except Exception as e:
        logger.error(f"Serper search failed: {e}")
        return None


async def _search_tavily(query: str, num_results: int) -> Optional[List[Dict[str, Any]]]:
    """Search using Tavily API."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                'api_key': config.TAVILY_API_KEY,
                'query': query,
                'max_results': num_results
            }
            
            async with session.post(
                'https://api.tavily.com/search',
                json=payload,
                timeout=10
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    for item in data.get('results', [])[:num_results]:
                        results.append({
                            'title': item.get('title', ''),
                            'snippet': item.get('content', ''),
                            'link': item.get('url', '')
                        })
                    
                    return results
                else:
                    logger.warning(f"Tavily returned status {response.status}")
                    return None
    
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return None


async def get_search_context(query: str, num_results: int = 3) -> str:
    """
    Get search results formatted as context for RAG.
    
    Args:
        query: Search query
        num_results: Number of results
    
    Returns:
        Formatted search context
    """
    results = await search_web(query, num_results)
    
    if not results:
        return ""
    
    context_parts = ["Web search results:"]
    
    for i, result in enumerate(results, 1):
        context_parts.append(f"\n{i}. {result['title']}")
        context_parts.append(f"   {result['snippet']}")
        context_parts.append(f"   Source: {result['link']}")
    
    return "\n".join(context_parts)


async def is_search_available() -> bool:
    """Check if any search API is configured."""
    return bool(config.SERPER_API_KEY or config.TAVILY_API_KEY)
