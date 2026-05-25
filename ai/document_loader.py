"""
Document loader for various file formats.
Supports PDF, DOCX, TXT, and Markdown files.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from PyPDF2 import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

logger = logging.getLogger(__name__)


def load_pdf(path: str) -> Optional[str]:
    """
    Load text from a PDF file.
    
    Args:
        path: Path to PDF file
    
    Returns:
        Extracted text or None if failed
    """
    if not PDF_AVAILABLE:
        logger.error("PyPDF2 not available")
        return None
    
    try:
        reader = PdfReader(path)
        text_parts = []
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        
        return '\n\n'.join(text_parts)
    
    except Exception as e:
        logger.error(f"Failed to load PDF {path}: {e}")
        return None


def load_docx(path: str) -> Optional[str]:
    """
    Load text from a DOCX file.
    
    Args:
        path: Path to DOCX file
    
    Returns:
        Extracted text or None if failed
    """
    if not DOCX_AVAILABLE:
        logger.error("python-docx not available")
        return None
    
    try:
        doc = Document(path)
        text_parts = []
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        
        return '\n\n'.join(text_parts)
    
    except Exception as e:
        logger.error(f"Failed to load DOCX {path}: {e}")
        return None


def load_txt(path: str) -> Optional[str]:
    """
    Load text from a TXT file.
    
    Args:
        path: Path to TXT file
    
    Returns:
        File content or None if failed
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load TXT {path}: {e}")
        return None


def load_md(path: str) -> Optional[str]:
    """
    Load text from a Markdown file.
    
    Args:
        path: Path to MD file
    
    Returns:
        File content or None if failed
    """
    return load_txt(path)  # Markdown is just text


def load_document(path: str) -> Optional[Dict[str, Any]]:
    """
    Load a document of any supported type.
    
    Args:
        path: Path to document
    
    Returns:
        Dictionary with document info or None if failed
    """
    path_obj = Path(path)
    
    if not path_obj.exists():
        logger.error(f"Document not found: {path}")
        return None
    
    suffix = path_obj.suffix.lower()
    text = None
    
    if suffix == '.pdf':
        text = load_pdf(path)
    elif suffix in ['.docx', '.doc']:
        text = load_docx(path)
    elif suffix == '.txt':
        text = load_txt(path)
    elif suffix in ['.md', '.markdown']:
        text = load_md(path)
    else:
        logger.warning(f"Unsupported file type: {suffix}")
        return None
    
    if text:
        return {
            'path': str(path),
            'filename': path_obj.name,
            'type': suffix,
            'content': text,
            'length': len(text)
        }
    
    return None


def iter_document_paths(directory: str, recursive: bool = True):
    """
    Yield paths to supported documents without loading file contents.
    Keeps peak RAM low during RAG indexing.
    """
    dir_path = Path(directory)

    if not dir_path.exists() or not dir_path.is_dir():
        logger.error(f"Invalid directory: {directory}")
        return

    extensions = [".pdf", ".docx", ".doc", ".txt", ".md", ".markdown"]
    if recursive:
        for ext in extensions:
            for file_path in dir_path.rglob(f"*{ext}"):
                yield file_path
    else:
        for ext in extensions:
            for file_path in dir_path.glob(f"*{ext}"):
                yield file_path


def load_directory(directory: str, recursive: bool = True) -> List[Dict[str, Any]]:
    """
    Load all supported documents from a directory.
    
    Args:
        directory: Directory path
        recursive: Search recursively
    
    Returns:
        List of loaded documents
    """
    dir_path = Path(directory)
    
    if not dir_path.exists() or not dir_path.is_dir():
        logger.error(f"Invalid directory: {directory}")
        return []
    
    documents = []
    
    # Supported extensions
    extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.markdown']
    
    # Get all files
    if recursive:
        files = []
        for ext in extensions:
            files.extend(dir_path.rglob(f'*{ext}'))
    else:
        files = []
        for ext in extensions:
            files.extend(dir_path.glob(f'*{ext}'))
    
    logger.info(f"Found {len(files)} documents in {directory}")
    
    for file_path in files:
        doc = load_document(str(file_path))
        if doc:
            documents.append(doc)
            logger.debug(f"Loaded: {file_path.name}")
    
    logger.info(f"Successfully loaded {len(documents)} documents")
    
    return documents


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Text to chunk
        chunk_size: Size of each chunk (in words)
        overlap: Overlap between chunks (in words)
    
    Returns:
        List of text chunks
    """
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks
