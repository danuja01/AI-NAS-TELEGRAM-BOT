"""
Ollama client for lightweight local AI tasks (fallback).
"""

import logging
import aiohttp
from typing import Optional

import config

logger = logging.getLogger(__name__)


async def generate_simple(prompt: str, model: str = "tinyllama") -> Optional[str]:
    """
    Generate simple responses using local Ollama.
    Used as fallback for trivial tasks to save API costs.
    
    Args:
        prompt: The prompt
        model: Ollama model to use
    
    Returns:
        Generated text or None if unavailable
    """
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            
            async with session.post(config.OLLAMA_URL, json=payload, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('response', '')
                else:
                    logger.warning(f"Ollama returned status {response.status}")
                    return None
    
    except aiohttp.ClientConnectorError:
        logger.debug("Ollama not available (connection failed)")
        return None
    except Exception as e:
        logger.warning(f"Ollama generation failed: {e}")
        return None


async def is_ollama_available() -> bool:
    """Check if Ollama is available."""
    try:
        async with aiohttp.ClientSession() as session:
            # Try a simple health check
            async with session.get(config.OLLAMA_URL.replace('/api/generate', '/'), timeout=5) as response:
                return response.status == 200
    except:
        return False
