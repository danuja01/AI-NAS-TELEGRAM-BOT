"""
OpenAI GPT client for AI tasks.
Primary AI engine using gpt-5.4-nano, gpt-5.4-mini, and o3.
"""

import json
import logging
from typing import List, Dict, Any

from openai import AsyncOpenAI

import config
from ai.agent_telegram import AgentTelegramBindings
from ai.nas_agent_tools import NAS_AGENT_TOOLS, dispatch_nas_agent_tool

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """
    Lazily construct the AsyncOpenAI client.

    Creating AsyncOpenAI with a missing api_key raises at construction time on current SDKs,
    which would break import-only smoke tests. Normal bot startup still requires a key via
    config.validate_config().
    """
    global _client
    if _client is None:
        key = config.OPENAI_API_KEY
        if not key:
            raise ValueError("OPENAI_API_KEY is required for AI operations")
        _client = AsyncOpenAI(api_key=key)
    return _client


def __getattr__(name: str) -> Any:
    """Lazy `client` attribute for callers that reference `gpt_client.client`."""
    if name == "client":
        return get_openai_client()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _model_ignores_temperature(model: str) -> bool:
    """Reasoning models (o1/o3) reject the temperature parameter on the Chat Completions API."""
    m = (model or "").lower().strip()
    return m.startswith("o1") or m.startswith("o3")


async def generate(
    prompt: str,
    context: str = "",
    system_prompt: str = None,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 2000
) -> str:
    """
    Generate text using OpenAI GPT models.
    
    Args:
        prompt: The user prompt
        context: Additional context (conversation history, retrieved docs, etc.)
        system_prompt: System prompt (defaults to DevOps assistant)
        model: Model to use (defaults to config.DEFAULT_MODEL)
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
    
    Returns:
        Generated text
    """
    if model is None:
        model = config.DEFAULT_MODEL
    
    if system_prompt is None:
        system_prompt = (
            "You are a concise, technical DevOps assistant managing a NAS server. "
            "Provide helpful, accurate information with minimal verbosity. "
            "Focus on practical solutions and clear explanations."
        )
    
    try:
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add context if provided
        if context:
            messages.append({
                "role": "system",
                "content": f"Context:\n{context}"
            })
        
        # Add user prompt
        messages.append({"role": "user", "content": prompt})
        
        logger.info(f"Generating with model: {model}")
        
        # ALL modern OpenAI models (GPT-5, o3) use max_completion_tokens
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if not _model_ignores_temperature(model):
            create_kwargs["temperature"] = temperature
        response = await get_openai_client().chat.completions.create(**create_kwargs)
        
        return response.choices[0].message.content
    
    except Exception as e:
        logger.error(f"GPT generation failed with {model}: {e}")
        
        # Try fallback model if not already using it
        if model != config.FALLBACK_MODEL:
            logger.info(f"Trying fallback model: {config.FALLBACK_MODEL}")
            try:
                return await generate(
                    prompt, context, system_prompt,
                    model=config.FALLBACK_MODEL,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as fallback_error:
                logger.error(f"Fallback model also failed: {fallback_error}")
        
        raise


async def generate_with_tools_loop(
    prompt: str,
    context: str = "",
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.5,
    max_tokens: int = 3500,
    max_tool_rounds: int | None = None,
    telegram_bindings: AgentTelegramBindings | None = None,
) -> str:
    """
    Chat completion with read-only NAS/Docker tools (function calling).

    Loops until the model returns a normal message or ``max_tool_rounds`` is exceeded.
    """
    if model is None:
        model = config.DEFAULT_MODEL
    if system_prompt is None:
        system_prompt = (
            "You are a concise technical assistant for a NAS Telegram bot. "
            "You have tools for THIS host: temperatures, health score, disks, network, SMART, "
            "per-device SMART detail, OpenMediaVault disk/filesystem/SMART RPC when the host exposes omv-rpc, systemd, "
            "storage paths, Docker reads, and **nas_request_docker_restart** / **nas_request_docker_stop** "
            "which post the same Telegram Confirm/Cancel buttons as /drestart and /dstop (nothing happens until the user confirms). "
            "For other destructive host actions, still point users to slash commands. "
            "Never use markdown pipe tables; use short bullet lists. "
            "Whenever the user asks about their own machine, call tools first; do not invent metrics."
        )
    rounds_limit = (
        max_tool_rounds if max_tool_rounds is not None else config.AGENT_MAX_TOOL_ROUNDS
    )

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({"role": "system", "content": f"Context:\n{context}"})
    messages.append({"role": "user", "content": prompt})

    client = get_openai_client()

    for _ in range(rounds_limit):
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": NAS_AGENT_TOOLS,
            "tool_choice": "auto",
            "max_completion_tokens": max_tokens,
        }
        if not _model_ignores_temperature(model):
            create_kwargs["temperature"] = temperature

        response = await client.chat.completions.create(**create_kwargs)
        msg = response.choices[0].message

        if msg.tool_calls:
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [],
            }
            for tc in msg.tool_calls:
                assistant_msg["tool_calls"].append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                )
            messages.append(assistant_msg)

            for tc in msg.tool_calls:
                fn = tc.function
                try:
                    args = json.loads(fn.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await dispatch_nas_agent_tool(fn.name, args, telegram_bindings)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )
            continue

        text = msg.content
        if text:
            return text
        return "(No text in model response.)"

    return (
        "Stopped: reached the maximum number of tool rounds without a final answer. "
        "Try a narrower question or raise AGENT_MAX_TOOL_ROUNDS in the environment."
    )


async def generate_with_thinking(
    prompt: str,
    context: str = "",
    system_prompt: str = None
) -> str:
    """
    Generate text using o3-mini for complex reasoning.
    
    Args:
        prompt: The user prompt requiring deep thinking
        context: Additional context
        system_prompt: Optional system prompt
    
    Returns:
        Generated text with reasoning
    """
    if system_prompt is None:
        system_prompt = (
            "You are an expert technical assistant with deep reasoning capabilities. "
            "Think through problems step by step and provide thorough, well-reasoned answers."
        )
    
    try:
        return await generate(
            prompt=prompt,
            context=context,
            system_prompt=system_prompt,
            model=config.THINKING_MODEL,
            temperature=0.5,  # Lower temperature for more focused reasoning
            max_tokens=3000
        )
    
    except Exception as e:
        logger.error(f"Thinking generation failed: {e}")
        # Fallback to default model
        return await generate(prompt, context, system_prompt)


async def generate_stream(
    prompt: str,
    context: str = "",
    system_prompt: str = None,
    model: str = None
):
    """
    Generate text with streaming (for real-time responses).
    
    Yields:
        Text chunks as they're generated
    """
    if model is None:
        model = config.DEFAULT_MODEL
    
    if system_prompt is None:
        system_prompt = (
            "You are a concise, technical DevOps assistant. "
            "Provide clear, practical information."
        )
    
    try:
        messages = [{"role": "system", "content": system_prompt}]
        
        if context:
            messages.append({"role": "system", "content": f"Context:\n{context}"})
        
        messages.append({"role": "user", "content": prompt})
        
        # Use max_completion_tokens for all modern models
        stream_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_completion_tokens": 2000,
        }
        if not _model_ignores_temperature(model):
            stream_kwargs["temperature"] = 0.7
        stream = await get_openai_client().chat.completions.create(**stream_kwargs)
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    except Exception as e:
        logger.error(f"Streaming generation failed: {e}")
        yield f"Error: {e}"


async def summarize_text(text: str, max_length: int = 200) -> str:
    """
    Summarize text to a specified length.
    
    Args:
        text: Text to summarize
        max_length: Maximum length of summary
    
    Returns:
        Summarized text
    """
    prompt = f"Summarize the following text in {max_length} words or less:\n\n{text}"
    
    return await generate(
        prompt=prompt,
        model=config.DEFAULT_MODEL,
        temperature=0.5,
        max_tokens=max_length * 2  # Words to tokens ratio
    )


async def analyze_error(error_message: str, context: str = "") -> str:
    """
    Analyze an error message and provide troubleshooting suggestions.
    
    Args:
        error_message: The error message
        context: Additional context about when the error occurred
    
    Returns:
        Analysis and suggestions
    """
    prompt = f"Analyze this error and provide troubleshooting steps:\n\nError: {error_message}"
    
    if context:
        prompt += f"\n\nContext: {context}"
    
    return await generate_with_thinking(prompt)
