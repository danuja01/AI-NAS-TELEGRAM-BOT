"""
RAG (Retrieval-Augmented Generation) engine.
Indexes documents and answers questions using ChromaDB + GPT.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("chromadb not available")

import config
from ai.agent_telegram import AgentTelegramBindings
from ai.bot_command_catalog import BOT_COMMAND_CATALOG
from ai.document_loader import load_directory, chunk_text
from ai.embeddings import embed_text, embed_batch, is_embeddings_available
from ai.gpt_client import generate_with_thinking, generate_with_tools_loop
from ai.conversation_history import ConversationManager
from ai.search_engine import get_search_context, is_search_available

logger = logging.getLogger(__name__)

# Global ChromaDB client and collection
_client = None
_collection = None


def get_chroma_client():
    """Get or initialize ChromaDB client."""
    global _client
    
    if not CHROMA_AVAILABLE:
        raise ImportError("chromadb not installed")
    
    if _client is None:
        logger.info(f"Initializing ChromaDB at {config.CHROMA_PATH}")
        _client = chromadb.Client(Settings(
            persist_directory=config.CHROMA_PATH,
            anonymized_telemetry=False
        ))
        logger.info("ChromaDB initialized")
    
    return _client


def get_collection(name: str = "documents"):
    """Get or create a ChromaDB collection."""
    global _collection
    
    if _collection is None:
        client = get_chroma_client()
        
        try:
            _collection = client.get_collection(name=name)
            logger.info(f"Loaded existing collection: {name}")
        except:
            _collection = client.create_collection(name=name)
            logger.info(f"Created new collection: {name}")
    
    return _collection


async def index_documents(directory_path: str = None, force_reindex: bool = False) -> Dict[str, Any]:
    """
    Index all documents in a directory.
    
    Args:
        directory_path: Path to directory (defaults to config.DOCUMENT_PATH)
        force_reindex: If True, clear existing index first
    
    Returns:
        Dictionary with indexing results
    """
    if not is_embeddings_available():
        raise ImportError("Embeddings not available")
    
    if directory_path is None:
        directory_path = config.DOCUMENT_PATH
    
    if not directory_path:
        raise ValueError("No document path specified")
    
    logger.info(f"Starting document indexing from {directory_path}")
    
    # Get collection
    collection = get_collection()
    
    # Clear existing if force reindex
    if force_reindex:
        logger.info("Force reindex: clearing existing collection")
        client = get_chroma_client()
        try:
            client.delete_collection("documents")
        except:
            pass
        collection = client.create_collection("documents")
    
    # Load documents
    logger.info("Loading documents...")
    documents = load_directory(directory_path, recursive=True)
    
    if not documents:
        return {
            'success': False,
            'message': 'No documents found',
            'documents_processed': 0
        }
    
    logger.info(f"Loaded {len(documents)} documents")
    
    # Process documents
    total_chunks = 0
    processed_docs = 0
    
    for doc in documents:
        try:
            # Chunk the document
            chunks = chunk_text(doc['content'], chunk_size=512, overlap=50)
            
            if not chunks:
                continue
            
            logger.info(f"Processing {doc['filename']}: {len(chunks)} chunks")
            
            # Generate embeddings
            embeddings = embed_batch(chunks)
            
            # Prepare metadata
            ids = [f"{doc['filename']}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    'filename': doc['filename'],
                    'path': doc['path'],
                    'type': doc['type'],
                    'chunk_index': i
                }
                for i in range(len(chunks))
            ]
            
            # Add to collection
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas
            )
            
            total_chunks += len(chunks)
            processed_docs += 1
            
            logger.info(f"Indexed {doc['filename']}")
        
        except Exception as e:
            logger.error(f"Failed to index {doc.get('filename', 'unknown')}: {e}")
            continue
    
    result = {
        'success': True,
        'message': f'Indexed {processed_docs} documents with {total_chunks} chunks',
        'documents_processed': processed_docs,
        'total_chunks': total_chunks
    }
    
    logger.info(f"Indexing complete: {result['message']}")
    
    return result


async def search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Search for relevant document chunks.
    
    Args:
        query: Search query
        top_k: Number of results to return
    
    Returns:
        List of relevant chunks with metadata
    """
    try:
        collection = get_collection()
        
        # Generate query embedding
        query_embedding = embed_text(query)
        
        # Search
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format results
        chunks = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                chunks.append({
                    'content': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'distance': results['distances'][0][i] if results['distances'] else None
                })
        
        return chunks
    
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


async def ask(
    question: str,
    user_id: int,
    use_thinking: bool = False,
    search_web: bool = False,
    telegram_bindings: AgentTelegramBindings | None = None,
) -> str:
    """
    Answer a question using RAG with conversation context.
    
    Args:
        question: The question to answer
        user_id: Telegram user ID (for conversation history)
        use_thinking: Use o3-mini for complex reasoning
        search_web: Include web search results
        telegram_bindings: When set (normal Telegram handler), agent tools can post Docker confirm UIs.
    
    Returns:
        Generated answer
    """
    try:
        # Get conversation history
        conv_context = await ConversationManager.format_for_rag(user_id)
        
        # Search for relevant document chunks
        relevant_chunks = await search(question, top_k=5)
        
        # Build context from retrieved documents
        doc_context_parts = []
        if relevant_chunks:
            doc_context_parts.append("Relevant information from documents:")
            for i, chunk in enumerate(relevant_chunks, 1):
                filename = chunk['metadata'].get('filename', 'Unknown')
                doc_context_parts.append(f"\n[Source {i}: {filename}]")
                doc_context_parts.append(chunk['content'])
        
        doc_context = "\n".join(doc_context_parts)
        
        # Add web search if requested
        web_context = ""
        if search_web and await is_search_available():
            logger.info("Including web search results")
            web_context = await get_search_context(question, num_results=3)
        
        # Combine all context
        full_context = ""
        full_context += f"## Bot commands (always available)\n{BOT_COMMAND_CATALOG}\n\n"
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
        rag_system = (
            "You are a helpful AI assistant for a NAS Telegram bot. Answer using the provided context. "
            "The command reference describes what users can type in Telegram. "
            "You have tools to read live data from this host (temperatures, disks, SMART, Docker, OpenMediaVault RPC when available, etc.). "
            "You may call **nas_request_docker_restart** or **nas_request_docker_stop** to post the same inline "
            "Confirm/Cancel prompts as /drestart and /dstop; nothing runs until the user confirms. "
            + rag_ro
            + "Put bot slash commands in markdown inline code (/command with backticks), not * or ** around commands. "
            + "Do not use markdown pipe tables in replies; use bullet lists. "
            "If the question is about the user's own NAS state, call tools first; do not invent readings. "
            "If the context does not contain the answer, say so. Be concise and accurate."
        )

        # Generate answer (read-only tools when not using a pure reasoning-only path)
        if use_thinking:
            answer = await generate_with_thinking(
                prompt=question,
                context=full_context
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
        logger.error(f"Failed to answer question: {e}", exc_info=True)
        return f"I encountered an error while processing your question: {e}"


def is_rag_ready() -> bool:
    """Check if RAG system is ready (collection exists and has documents)."""
    try:
        collection = get_collection()
        count = collection.count()
        return count > 0
    except:
        return False


def get_index_stats() -> Dict[str, Any]:
    """Get statistics about the indexed documents."""
    try:
        collection = get_collection()
        count = collection.count()
        
        return {
            'total_chunks': count,
            'ready': count > 0
        }
    except Exception as e:
        return {
            'error': str(e),
            'ready': False
        }
