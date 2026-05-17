"""
AI command handlers for RAG, chat, and search functionality.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit
from utils.formatters import format_error, format_success, format_ai_response
from ai.rag_engine import ask, index_documents, is_rag_ready, get_index_stats
from ai.gpt_client import generate, generate_with_thinking, summarize_text
from ai.search_engine import search_web, is_search_available
from ai.conversation_history import ConversationManager
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)


@require_auth
@rate_limit
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command - RAG-powered Q&A over documents."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/ask <your question>`\n\n"
            "Example: `/ask What are IELTS speaking tips?`",
            parse_mode='Markdown'
        )
        return
    
    question = ' '.join(context.args)
    
    try:
        # Check if RAG is ready
        if not is_rag_ready():
            await update.message.reply_text(
                "⚠️ Document index is empty.\n\n"
                "Use `/index` to index documents first.",
                parse_mode='Markdown'
            )
            return
        
        await update.message.reply_text("🤔 Searching documents and thinking...")
        
        # Ask with conversation context
        answer = await ask(question, user_id, use_thinking=False, search_web=False)
        
        # Format for Telegram
        formatted_answer = format_ai_response(answer)
        await update.message.reply_text(formatted_answer, parse_mode='Markdown')
        
        # Save to conversation history
        await ConversationManager.add_message(user_id, 'user', question)
        await ConversationManager.add_message(user_id, 'assistant', answer)
        await save_command(user_id, f'/ask {question}', 'RAG query')
        
    except Exception as e:
        logger.error(f"Error in ask_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to answer question: {e}"))


@require_auth
@rate_limit
async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chat command - General AI chat with history."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/chat <your message>`\n\n"
            "Example: `/chat How do I secure my Docker containers?`",
            parse_mode='Markdown'
        )
        return
    
    message = ' '.join(context.args)
    
    try:
        await update.message.reply_text("💬 Thinking...")
        
        # Get conversation context
        conv_context = await ConversationManager.format_for_rag(user_id, limit=5)
        
        # Generate response
        response = await generate(
            prompt=message,
            context=conv_context,
            system_prompt=(
                "You are a helpful DevOps and NAS management assistant. "
                "Provide clear, practical advice."
            )
        )
        
        # Format for Telegram
        formatted_response = format_ai_response(response)
        await update.message.reply_text(formatted_response, parse_mode='Markdown')
        
        # Save to conversation history
        await ConversationManager.add_message(user_id, 'user', message)
        await ConversationManager.add_message(user_id, 'assistant', response)
        await save_command(user_id, f'/chat {message[:50]}', 'Chat')
        
    except Exception as e:
        logger.error(f"Error in chat_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Chat failed: {e}"))


@require_auth
@rate_limit
async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /summarize command - Summarize documents about a topic."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/summarize <topic>`\n\n"
            "Example: `/summarize writing task 2`",
            parse_mode='Markdown'
        )
        return
    
    topic = ' '.join(context.args)
    
    try:
        if not is_rag_ready():
            await update.message.reply_text(
                "⚠️ Document index is empty. Use `/index` first.",
                parse_mode='Markdown'
            )
            return
        
        await update.message.reply_text("📝 Gathering information and summarizing...")
        
        # Use RAG to find relevant info
        answer = await ask(
            f"Provide a comprehensive summary of information about: {topic}",
            user_id,
            use_thinking=False
        )
        
        # Format for Telegram
        formatted_answer = format_ai_response(answer)
        await update.message.reply_text(f"**Summary: {topic}**\n\n{formatted_answer}", parse_mode='Markdown')
        
        # Save to conversation history
        await ConversationManager.add_message(user_id, 'user', f'/summarize {topic}')
        await ConversationManager.add_message(user_id, 'assistant', answer)
        await save_command(user_id, f'/summarize {topic}', 'Summarize')
        
    except Exception as e:
        logger.error(f"Error in summarize_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Summarization failed: {e}"))


@require_auth
@rate_limit
async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /explain command - Explain a term from documents."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/explain <term>`\n\n"
            "Example: `/explain band score`",
            parse_mode='Markdown'
        )
        return
    
    term = ' '.join(context.args)
    
    try:
        if not is_rag_ready():
            await update.message.reply_text(
                "⚠️ Document index is empty. Use `/index` first.",
                parse_mode='Markdown'
            )
            return
        
        await update.message.reply_text(f"📚 Looking up '{term}'...")
        
        answer = await ask(f"Explain what '{term}' means", user_id)
        
        # Format for Telegram
        formatted_answer = format_ai_response(answer)
        await update.message.reply_text(f"**Explanation: {term}**\n\n{formatted_answer}", parse_mode='Markdown')
        
        # Save to conversation history
        await ConversationManager.add_message(user_id, 'user', f'/explain {term}')
        await ConversationManager.add_message(user_id, 'assistant', answer)
        await save_command(user_id, f'/explain {term}', 'Explain')
        
    except Exception as e:
        logger.error(f"Error in explain_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Explanation failed: {e}"))


@require_auth
@rate_limit
async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /analyze command - Deep analysis using o3-mini."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/analyze <text or question>`\n\n"
            "Example: `/analyze Why is my CPU usage high?`",
            parse_mode='Markdown'
        )
        return
    
    text = ' '.join(context.args)
    
    try:
        await update.message.reply_text("🧠 Analyzing with advanced reasoning (o3)...")
        
        # Get conversation context (may include recent command outputs)
        conv_context = await ConversationManager.format_for_rag(user_id, limit=5)
        
        # Use thinking model for deep analysis
        analysis = await generate_with_thinking(
            prompt=text,
            context=conv_context
        )
        
        # Format for Telegram
        formatted_analysis = format_ai_response(analysis)
        await update.message.reply_text(f"**Analysis:**\n\n{formatted_analysis}", parse_mode='Markdown')
        
        # Save to conversation history
        await ConversationManager.add_message(user_id, 'user', f'/analyze {text}')
        await ConversationManager.add_message(user_id, 'assistant', analysis)
        await save_command(user_id, f'/analyze', 'Analysis')
        
    except Exception as e:
        logger.error(f"Error in analyze_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Analysis failed: {e}"))


@require_auth
@rate_limit
async def think_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /think command - Complex reasoning with o3-mini."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/think <complex question>`\n\n"
            "Example: `/think What's the best backup strategy for my NAS?`",
            parse_mode='Markdown'
        )
        return
    
    question = ' '.join(context.args)
    
    try:
        await update.message.reply_text("🤔 Deep thinking with o3 (this may take longer)...")
        
        # Get conversation context
        conv_context = await ConversationManager.format_for_rag(user_id, limit=5)
        
        # Use thinking model
        answer = await generate_with_thinking(
            prompt=question,
            context=conv_context
        )
        
        # Format for Telegram
        formatted_answer = format_ai_response(answer)
        await update.message.reply_text(formatted_answer, parse_mode='Markdown')
        
        # Save to conversation history
        await ConversationManager.add_message(user_id, 'user', f'/think {question}')
        await ConversationManager.add_message(user_id, 'assistant', answer)
        await save_command(user_id, f'/think', 'Thinking')
        
    except Exception as e:
        logger.error(f"Error in think_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Thinking failed: {e}"))


@require_auth
@rate_limit
async def websearch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /websearch command - Internet search with AI summary."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/websearch <query>`\n\n"
            "Example: `/websearch latest Docker security best practices`",
            parse_mode='Markdown'
        )
        return
    
    query = ' '.join(context.args)
    
    try:
        if not await is_search_available():
            await update.message.reply_text(
                "⚠️ Web search not available.\n\n"
                "Configure SERPER_API_KEY or TAVILY_API_KEY in .env file.",
                parse_mode='Markdown'
            )
            return
        
        await update.message.reply_text(f"🔍 Searching the web for '{query}'...")
        
        # Search the web
        results = await search_web(query, num_results=5)
        
        if not results:
            await update.message.reply_text("❌ No search results found")
            return
        
        # Format results
        message = f"🔍 **Search Results: {query}**\n\n"
        
        for i, result in enumerate(results, 1):
            message += f"**{i}. {result['title']}**\n"
            message += f"{result['snippet']}\n"
            message += f"🔗 {result['link']}\n\n"
        
        # Generate AI summary
        search_text = "\n".join([f"{r['title']}: {r['snippet']}" for r in results])
        summary = await summarize_text(f"Summarize these search results about '{query}':\n\n{search_text}", max_length=150)
        
        # Format summary for Telegram
        formatted_summary = format_ai_response(summary)
        message += f"**AI Summary:**\n{formatted_summary}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await ConversationManager.add_message(user_id, 'user', f'/websearch {query}')
        await ConversationManager.add_message(user_id, 'assistant', summary)
        await save_command(user_id, f'/websearch {query}', f"{len(results)} results")
        
    except Exception as e:
        logger.error(f"Error in websearch_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Search failed: {e}"))


@require_auth
@rate_limit
async def index_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /index command - Index documents for RAG."""
    user_id = update.effective_user.id
    
    try:
        # Check current status
        stats = get_index_stats()
        
        await update.message.reply_text(
            "📚 Starting document indexing...\n\n"
            "This may take a few minutes depending on the number of documents.",
            parse_mode='Markdown'
        )
        
        # Index documents
        result = await index_documents(force_reindex=False)
        
        if result['success']:
            message = format_success(
                f"Indexing complete!\n\n"
                f"📄 Documents: {result['documents_processed']}\n"
                f"📦 Chunks: {result['total_chunks']}"
            )
        else:
            message = format_error(result.get('message', 'Indexing failed'))
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await save_command(user_id, '/index', result['message'])
        
    except Exception as e:
        logger.error(f"Error in index_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Indexing failed: {e}"))


@require_auth
@rate_limit
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command - Clear conversation history."""
    user_id = update.effective_user.id
    
    try:
        await ConversationManager.clear(user_id)
        
        await update.message.reply_text(
            format_success("Conversation history cleared! Starting fresh.")
        )
        
        await save_command(user_id, '/clear', 'History cleared')
        
    except Exception as e:
        logger.error(f"Error in clear_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to clear history: {e}"))
