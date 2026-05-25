"""
RAG (Retrieval-Augmented Generation) engine.
Indexes documents and answers questions using ChromaDB + GPT.
"""

import logging
from typing import List, Dict, Any, Optional

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("chromadb not available")

import config
from ai.agent_telegram import AgentTelegramBindings
from ai.document_loader import iter_document_paths, load_document, chunk_text
from ai.embeddings import embed_text, embed_batch, is_embeddings_available
from ai.gpt_client import generate_with_thinking, generate_with_tools_loop
from ai.prompt_scope import with_nas_scope
from ai.conversation_history import ConversationManager
from ai.search_engine import get_search_context, is_search_available

logger = logging.getLogger(__name__)

# Global ChromaDB client and collection
_client = None
_collection = None


def get_chroma_client():
    """Get or initialize ChromaDB persistent client."""
    global _client

    if not CHROMA_AVAILABLE:
        raise ImportError("chromadb not installed")

    if _client is None:
        logger.info("Initializing ChromaDB at %s", config.CHROMA_PATH)
        _client = chromadb.PersistentClient(path=config.CHROMA_PATH)
        logger.info("ChromaDB initialized")

    return _client


def get_collection(name: str = "documents"):
    """Get or create a ChromaDB collection."""
    global _collection

    if _collection is None:
        client = get_chroma_client()

        try:
            _collection = client.get_collection(name=name)
            logger.info("Loaded existing collection: %s", name)
        except Exception:
            _collection = client.create_collection(name=name)
            logger.info("Created new collection: %s", name)

    return _collection


def _reset_collection(force_reindex: bool) -> None:
    """Clear and recreate the documents collection when force reindexing."""
    global _collection
    if not force_reindex:
        return
    logger.info("Force reindex: clearing existing collection")
    client = get_chroma_client()
    try:
        client.delete_collection("documents")
    except Exception:
        pass
    _collection = client.create_collection("documents")


async def index_documents(directory_path: str = None, force_reindex: bool = False) -> Dict[str, Any]:
    """
    Index all documents in a directory (one file at a time to limit RAM spikes).
    """
    if not is_embeddings_available():
        raise ImportError(
            f"Embeddings not available (provider={config.EMBEDDING_PROVIDER}). "
            "Set OPENAI_API_KEY or EMBEDDING_PROVIDER=local with sentence-transformers installed."
        )

    if directory_path is None:
        directory_path = config.DOCUMENT_PATH

    if not directory_path:
        raise ValueError("No document path specified")

    logger.info("Starting document indexing from %s", directory_path)

    _reset_collection(force_reindex)
    collection = get_collection()

    total_chunks = 0
    processed_docs = 0
    paths = list(iter_document_paths(directory_path, recursive=True))

    if not paths:
        return {
            "success": False,
            "message": "No documents found",
            "documents_processed": 0,
        }

    logger.info("Found %s documents to index", len(paths))

    for file_path in paths:
        doc = load_document(str(file_path))
        if not doc:
            continue
        try:
            chunks = chunk_text(doc["content"], chunk_size=512, overlap=50)
            del doc["content"]

            if not chunks:
                continue

            logger.info("Processing %s: %s chunks", doc["filename"], len(chunks))

            embeddings = embed_batch(chunks, batch_size=config.EMBEDDING_BATCH_SIZE)

            ids = [f"{doc['filename']}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "filename": doc["filename"],
                    "path": doc["path"],
                    "type": doc["type"],
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )

            total_chunks += len(chunks)
            processed_docs += 1
            logger.info("Indexed %s", doc["filename"])

        except Exception as e:
            logger.error("Failed to index %s: %s", file_path.name, e)
            continue

    result = {
        "success": processed_docs > 0,
        "message": f"Indexed {processed_docs} documents with {total_chunks} chunks",
        "documents_processed": processed_docs,
        "total_chunks": total_chunks,
    }

    logger.info("Indexing complete: %s", result["message"])
    return result


async def search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search for relevant document chunks."""
    try:
        collection = get_collection()
        query_embedding = embed_text(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        chunks = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                chunks.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })

        return chunks

    except Exception as e:
        logger.error("Search failed: %s", e)
        return []


def _command_catalog_context() -> str:
    if not config.RAG_INCLUDE_COMMAND_CATALOG:
        return ""
    from ai.bot_command_catalog import BOT_COMMAND_CATALOG

    return f"## Bot commands (always available)\n{BOT_COMMAND_CATALOG}\n\n"


async def ask(
    question: str,
    user_id: int,
    use_thinking: bool = False,
    search_web: bool = False,
    telegram_bindings: AgentTelegramBindings | None = None,
) -> str:
    """Answer a question using RAG with conversation context."""
    try:
        conv_context = await ConversationManager.format_for_rag(user_id)
        relevant_chunks = await search(question, top_k=5)

        doc_context_parts = []
        if relevant_chunks:
            doc_context_parts.append("Relevant information from documents:")
            for i, chunk in enumerate(relevant_chunks, 1):
                filename = chunk["metadata"].get("filename", "Unknown")
                doc_context_parts.append(f"\n[Source {i}: {filename}]")
                doc_context_parts.append(chunk["content"])

        doc_context = "\n".join(doc_context_parts)

        web_context = ""
        if search_web and await is_search_available():
            logger.info("Including web search results")
            web_context = await get_search_context(question, num_results=3)

        full_context = _command_catalog_context()
        if conv_context:
            full_context += f"{conv_context}\n\n"
        if doc_context:
            full_context += f"{doc_context}\n\n"
        if web_context:
            full_context += f"{web_context}\n\n"

        rag_ro = ""
        if config.AGENT_HOST_READONLY_TOOL:
            rag_ro = (
                "When AGENT_HOST_READONLY_TOOL is enabled, **nas_host_readonly_profile** may appear: allow-listed read-only "
                "host diagnostics over SSH/nsenter (fixed argv, not arbitrary shell); it **does not** replace **`/ssh`**. "
            )
        rag_system = with_nas_scope(
            "You are a helpful AI assistant for a NAS Telegram bot. Answer using the provided context. "
            "The command reference describes what users can type in Telegram. "
            "You have tools to read live data from this host (temperatures, **nas_cpu_stats** for per-core CPU, disks, SMART, Docker, OpenMediaVault RPC when available, etc.). "
            "You may call **nas_request_docker_restart** or **nas_request_docker_stop** to post the same inline "
            "Confirm/Cancel prompts as /drestart and /dstop; nothing runs until the user confirms. "
            + rag_ro
            + "For **unused Docker images** or reclaimable image space, point users to `/dimages` or `/dscan`, not `/docker` (dashboard only). "
            + "The `Recent conversation context` section may include the bot's own prior messages (slash-command output or "
            "automated alerts); treat it as what the user refers to. "
            + "Put bot slash commands in markdown inline code (/command with backticks), not * or ** around commands. "
            + "Do not use markdown pipe tables in replies; use bullet lists. "
            + "If the question is about the user's own NAS state, call tools first; do not invent readings. "
            + "For **per-core CPU**, call **nas_cpu_stats** (or **nas_system_health_snapshot**) before claiming data is unavailable. "
            + "If the context does not contain the answer, say so. Be concise and accurate."
        )

        if use_thinking:
            answer = await generate_with_thinking(
                prompt=question,
                context=full_context,
            )
        else:
            answer = await generate_with_tools_loop(
                prompt=question,
                context=full_context,
                system_prompt=rag_system,
                model=config.DEFAULT_MODEL,
                temperature=0.4,
                max_tokens=3500,
                telegram_bindings=telegram_bindings,
                nas_tools_for_rag=True,
            )

        return answer

    except Exception as e:
        logger.error("Failed to answer question: %s", e, exc_info=True)
        return f"I encountered an error while processing your question: {e}"


def is_rag_ready() -> bool:
    """Check if RAG system is ready (collection exists and has documents)."""
    try:
        collection = get_collection()
        return collection.count() > 0
    except Exception:
        return False


def get_index_stats() -> Dict[str, Any]:
    """Get statistics about the indexed documents."""
    try:
        collection = get_collection()
        count = collection.count()

        return {
            "total_chunks": count,
            "ready": count > 0,
        }
    except Exception as e:
        return {
            "error": str(e),
            "ready": False,
        }
