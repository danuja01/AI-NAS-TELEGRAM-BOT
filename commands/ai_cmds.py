"""
AI command handlers for RAG, chat, and search functionality.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit
from utils.formatters import format_error, format_success, format_ai_response
from utils.telegram_reply import reply_text_chunked
from ai.rag_engine import ask, index_documents, is_rag_ready, get_index_stats
from ai.gpt_client import generate, generate_with_thinking, summarize_text
from ai.search_engine import search_web, is_search_available
from ai.conversation_history import ConversationManager
from database.memory import save_conversation, save_command
from utils.followup_state import (
    clear_ai_pending,
    clear_all_followup,
    get_ai_pending,
    get_cmd_pending,
    set_ai_pending_exclusive,
)

logger = logging.getLogger(__name__)

# When users pick /ask, /analyze, etc. from the Telegram menu, the client often sends
# the command alone. Plain-text routing lives in commands.text_followup (followup_state).

_PENDING_HINTS = {
    "ask": (
        "You used /ask without a question.\n\n"
        "Send your **next message** as the question, or /cancel to abort."
    ),
    "chat": (
        "You used /chat without text.\n\n"
        "Send your **next message** as your chat prompt, or /cancel."
    ),
    "summarize": (
        "You used /summarize without a topic.\n\n"
        "Send your **next message** as the topic to summarize, or /cancel."
    ),
    "explain": (
        "You used /explain without a term.\n\n"
        "Send your **next message** as the term to explain, or /cancel."
    ),
    "analyze": (
        "You used /analyze without text.\n\n"
        "Send your **next message** as what to analyze, or /cancel."
    ),
    "think": (
        "You used /think without a question.\n\n"
        "Send your **next message** as your question, or /cancel."
    ),
    "websearch": (
        "You used /websearch without a query.\n\n"
        "Send your **next message** as your search query, or /cancel."
    ),
}


@require_auth
async def cancel_pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abort waiting for follow-up text (AI or command prompts such as /restart)."""
    had = get_ai_pending(context) is not None or get_cmd_pending(context) is not None
    clear_all_followup(context)
    if had:
        await update.message.reply_text("Cancelled. You can run another command.")
    else:
        await update.message.reply_text("Nothing to cancel.")


async def execute_ask(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, question: str):
    try:
        if not is_rag_ready():
            await update.message.reply_text(
                "⚠️ Document index is empty.\n\n"
                "Use `/index` to index documents first.",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text("🤔 Searching documents and thinking...")

        answer = await ask(question, user_id, use_thinking=False, search_web=False)

        formatted_answer = format_ai_response(answer)
        await reply_text_chunked(update, formatted_answer, parse_mode="Markdown")

        await ConversationManager.add_message(user_id, "user", question)
        await ConversationManager.add_message(user_id, "assistant", answer)
        await save_command(user_id, f"/ask {question}", "RAG query")

    except Exception as e:
        logger.error("Error in execute_ask: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Failed to answer question: {e}"))


async def execute_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, message: str):
    try:
        await update.message.reply_text("💬 Thinking...")

        conv_context = await ConversationManager.format_for_rag(user_id, limit=5)

        response = await generate(
            prompt=message,
            context=conv_context,
            system_prompt=(
                "You are a helpful DevOps and NAS management assistant. "
                "Provide clear, practical advice."
            ),
        )

        formatted_response = format_ai_response(response)
        await reply_text_chunked(update, formatted_response, parse_mode="Markdown")

        await ConversationManager.add_message(user_id, "user", message)
        await ConversationManager.add_message(user_id, "assistant", response)
        await save_command(user_id, f"/chat {message[:50]}", "Chat")

    except Exception as e:
        logger.error("Error in execute_chat: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Chat failed: {e}"))


async def execute_summarize(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, topic: str
):
    try:
        if not is_rag_ready():
            await update.message.reply_text(
                "⚠️ Document index is empty. Use `/index` first.",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text("📝 Gathering information and summarizing...")

        answer = await ask(
            f"Provide a comprehensive summary of information about: {topic}",
            user_id,
            use_thinking=False,
        )

        formatted_answer = format_ai_response(answer)
        await reply_text_chunked(
            update, f"**Summary: {topic}**\n\n{formatted_answer}", parse_mode="Markdown"
        )

        await ConversationManager.add_message(user_id, "user", f"/summarize {topic}")
        await ConversationManager.add_message(user_id, "assistant", answer)
        await save_command(user_id, f"/summarize {topic}", "Summarize")

    except Exception as e:
        logger.error("Error in execute_summarize: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Summarization failed: {e}"))


async def execute_explain(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, term: str):
    try:
        if not is_rag_ready():
            await update.message.reply_text(
                "⚠️ Document index is empty. Use `/index` first.",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(f"📚 Looking up '{term}'...")

        answer = await ask(f"Explain what '{term}' means", user_id)

        formatted_answer = format_ai_response(answer)
        await reply_text_chunked(
            update, f"**Explanation: {term}**\n\n{formatted_answer}", parse_mode="Markdown"
        )

        await ConversationManager.add_message(user_id, "user", f"/explain {term}")
        await ConversationManager.add_message(user_id, "assistant", answer)
        await save_command(user_id, f"/explain {term}", "Explain")

    except Exception as e:
        logger.error("Error in execute_explain: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Explanation failed: {e}"))


async def execute_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str):
    try:
        await update.message.reply_text("🧠 Analyzing with advanced reasoning (o3)...")

        conv_context = await ConversationManager.format_for_rag(user_id, limit=5)

        analysis = await generate_with_thinking(prompt=text, context=conv_context)

        formatted_analysis = format_ai_response(analysis)
        await reply_text_chunked(
            update, f"**Analysis:**\n\n{formatted_analysis}", parse_mode="Markdown"
        )

        await ConversationManager.add_message(user_id, "user", f"/analyze {text}")
        await ConversationManager.add_message(user_id, "assistant", analysis)
        await save_command(user_id, "/analyze", "Analysis")

    except Exception as e:
        logger.error("Error in execute_analyze: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Analysis failed: {e}"))


async def execute_think(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, question: str):
    try:
        await update.message.reply_text("🤔 Deep thinking with o3 (this may take longer)...")

        conv_context = await ConversationManager.format_for_rag(user_id, limit=5)

        answer = await generate_with_thinking(prompt=question, context=conv_context)

        formatted_answer = format_ai_response(answer)
        await reply_text_chunked(update, formatted_answer, parse_mode="Markdown")

        await ConversationManager.add_message(user_id, "user", f"/think {question}")
        await ConversationManager.add_message(user_id, "assistant", answer)
        await save_command(user_id, "/think", "Thinking")

    except Exception as e:
        logger.error("Error in execute_think: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Thinking failed: {e}"))


async def execute_websearch(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, query: str):
    try:
        if not await is_search_available():
            await update.message.reply_text(
                "⚠️ Web search not available.\n\n"
                "Configure SERPER_API_KEY or TAVILY_API_KEY in .env file.",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(f"🔍 Searching the web for '{query}'...")

        results = await search_web(query, num_results=5)

        if not results:
            await update.message.reply_text("❌ No search results found")
            return

        message = f"🔍 **Search Results: {query}**\n\n"

        for i, result in enumerate(results, 1):
            message += f"**{i}. {result['title']}**\n"
            message += f"{result['snippet']}\n"
            message += f"🔗 {result['link']}\n\n"

        search_text = "\n".join([f"{r['title']}: {r['snippet']}" for r in results])
        summary = await summarize_text(
            f"Summarize these search results about '{query}':\n\n{search_text}",
            max_length=150,
        )

        formatted_summary = format_ai_response(summary)
        message += f"**AI Summary:**\n{formatted_summary}"

        await reply_text_chunked(update, message, parse_mode="Markdown")

        await ConversationManager.add_message(user_id, "user", f"/websearch {query}")
        await ConversationManager.add_message(user_id, "assistant", summary)
        await save_command(user_id, f"/websearch {query}", f"{len(results)} results")

    except Exception as e:
        logger.error("Error in execute_websearch: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Search failed: {e}"))


@require_auth
@rate_limit
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command - RAG-powered Q&A over documents."""
    user_id = update.effective_user.id

    clear_all_followup(context)
    if not context.args:
        set_ai_pending_exclusive(context, "ask")
        await update.message.reply_text(_PENDING_HINTS["ask"], parse_mode="Markdown")
        return

    question = " ".join(context.args)
    await execute_ask(update, context, user_id, question)


@require_auth
@rate_limit
async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chat command - General AI chat with history."""
    user_id = update.effective_user.id

    clear_all_followup(context)
    if not context.args:
        set_ai_pending_exclusive(context, "chat")
        await update.message.reply_text(_PENDING_HINTS["chat"], parse_mode="Markdown")
        return

    message = " ".join(context.args)
    await execute_chat(update, context, user_id, message)


@require_auth
@rate_limit
async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /summarize command - Summarize documents about a topic."""
    user_id = update.effective_user.id

    clear_all_followup(context)
    if not context.args:
        set_ai_pending_exclusive(context, "summarize")
        await update.message.reply_text(_PENDING_HINTS["summarize"], parse_mode="Markdown")
        return

    topic = " ".join(context.args)
    await execute_summarize(update, context, user_id, topic)


@require_auth
@rate_limit
async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /explain command - Explain a term from documents."""
    user_id = update.effective_user.id

    clear_all_followup(context)
    if not context.args:
        set_ai_pending_exclusive(context, "explain")
        await update.message.reply_text(_PENDING_HINTS["explain"], parse_mode="Markdown")
        return

    term = " ".join(context.args)
    await execute_explain(update, context, user_id, term)


@require_auth
@rate_limit
async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /analyze command - Deep analysis using o3-mini."""
    user_id = update.effective_user.id

    clear_all_followup(context)
    if not context.args:
        set_ai_pending_exclusive(context, "analyze")
        await update.message.reply_text(_PENDING_HINTS["analyze"], parse_mode="Markdown")
        return

    text = " ".join(context.args)
    await execute_analyze(update, context, user_id, text)


@require_auth
@rate_limit
async def think_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /think command - Complex reasoning with o3-mini."""
    user_id = update.effective_user.id

    clear_all_followup(context)
    if not context.args:
        set_ai_pending_exclusive(context, "think")
        await update.message.reply_text(_PENDING_HINTS["think"], parse_mode="Markdown")
        return

    question = " ".join(context.args)
    await execute_think(update, context, user_id, question)


@require_auth
@rate_limit
async def websearch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /websearch command - Internet search with AI summary."""
    user_id = update.effective_user.id

    clear_all_followup(context)
    if not context.args:
        set_ai_pending_exclusive(context, "websearch")
        await update.message.reply_text(_PENDING_HINTS["websearch"], parse_mode="Markdown")
        return

    query = " ".join(context.args)
    await execute_websearch(update, context, user_id, query)


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
        clear_all_followup(context)

        await update.message.reply_text(
            format_success("Conversation history cleared! Starting fresh.")
        )
        
        await save_command(user_id, '/clear', 'History cleared')
        
    except Exception as e:
        logger.error(f"Error in clear_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to clear history: {e}"))
