"""
Conversation history manager for context-aware AI responses.
"""

import logging
from typing import List, Dict, Any

from database.memory import (
    save_conversation as db_save_conversation,
    get_recent_context as db_get_recent_context,
    build_context_string as db_build_context_string,
    clear_conversation_history as db_clear_conversation_history
)

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manager for conversation context."""
    
    @staticmethod
    async def add_message(user_id: int, role: str, content: str, metadata: Dict[str, Any] = None):
        """
        Add a message to conversation history.
        
        Args:
            user_id: Telegram user ID
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata
        """
        await db_save_conversation(user_id, role, content, metadata=metadata)
    
    @staticmethod
    async def add_command_result(user_id: int, command: str, output: str):
        """
        Add a command result to conversation history.
        
        Args:
            user_id: Telegram user ID
            command: The command that was executed
            output: Command output/result
        """
        await db_save_conversation(
            user_id,
            role='assistant',
            message=f"Command: {command}",
            command_output=output
        )
    
    @staticmethod
    async def get_context(user_id: int, limit: int = None) -> List[Dict[str, Any]]:
        """
        Get recent conversation context.
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of messages
        
        Returns:
            List of conversation messages
        """
        return await db_get_recent_context(user_id, limit)
    
    @staticmethod
    async def format_for_rag(user_id: int, limit: int = None) -> str:
        """
        Format conversation history for RAG context.
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of messages
        
        Returns:
            Formatted context string
        """
        return await db_build_context_string(user_id, limit)
    
    @staticmethod
    async def clear(user_id: int):
        """
        Clear conversation history for a user.
        
        Args:
            user_id: Telegram user ID
        """
        await db_clear_conversation_history(user_id)
    
    @staticmethod
    async def get_last_command_output(user_id: int) -> str:
        """
        Get the output from the last command in conversation history.
        Useful for follow-up questions.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            Last command output or empty string
        """
        messages = await db_get_recent_context(user_id, limit=5)
        
        # Find most recent message with command_output
        for msg in reversed(messages):
            if msg.get('command_output'):
                return msg['command_output']
        
        return ""
