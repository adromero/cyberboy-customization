#!/usr/bin/env python3
"""
CyberRAG - Local RAG system for Cyberboy
Indexes Wikipedia, logs, and custom code for AI-powered queries
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Paths
HOME = Path.home()
DATA_DIR = HOME / ".cyberrag"
CHROMA_DIR = DATA_DIR / "chroma"
CODE_DIR = HOME / "customization"
KIWIX_DIR = HOME / "offline-library" / "kiwix"
DOCS_DIR = HOME / "offline-library" / "medical"
WIKIPEDIA_ZIM = KIWIX_DIR / "wikipedia_en_all_nopic_2025-12.zim"
WIKIBOOKS_ZIM = KIWIX_DIR / "wikibooks_en_all_maxi_2025-10.zim"

# Collections
COLLECTION_CODE = "code"
COLLECTION_LOGS = "logs"
COLLECTION_WIKI = "wikipedia"
COLLECTION_DOCS = "docs"

# Ollama config
OLLAMA_MODEL = "phi3:mini"
OLLAMA_URL = "http://localhost:11434"


def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    CHROMA_DIR.mkdir(exist_ok=True)


def get_chroma_client():
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_embedding_model():
    print("Loading embedding model...", file=sys.stderr)
    return SentenceTransformer('all-MiniLM-L6-v2')


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def index_code(model: SentenceTransformer, client: chromadb.Client, paths: list[str] = None):
    """Index Python files and configs from customization directory."""
    collection = client.get_or_create_collection(
        name=COLLECTION_CODE,
        metadata={"description": "Custom code and configs"}
    )

    # Clear existing
    existing = collection.get()
    if existing['ids']:
        collection.delete(ids=existing['ids'])

    search_paths = paths if paths else [CODE_DIR]
    extensions = {'.py', '.sh', '.conf', '.ini', '.xml', '.json', '.md', '.txt'}

    documents = []
    metadatas = []
    ids = []

    for search_path in search_paths:
        path = Path(search_path)
        if path.is_file():
            files = [path]
        else:
            files = list(path.rglob('*'))

        for f in files:
            if f.is_file() and f.suffix in extensions:
                try:
                    content = f.read_text(errors='ignore')
                    if len(content.strip()) < 10:
                        continue

                    # Add file header
                    header = f"# File: {f.name}\n# Path: {f}\n\n"
                    chunks = chunk_text(header + content, chunk_size=400)

                    for i, chunk in enumerate(chunks):
                        documents.append(chunk)
                        metadatas.append({
                            "source": str(f),
                            "filename": f.name,
                            "type": "code",
                            "chunk": i
                        })
                        ids.append(f"{f}_{i}")

                    print(f"  Indexed: {f.name} ({len(chunks)} chunks)")
                except Exception as e:
                    print(f"  Error reading {f}: {e}", file=sys.stderr)

    if documents:
        print(f"Generating embeddings for {len(documents)} chunks...")
        embeddings = model.encode(documents, show_progress_bar=True).tolist()
        collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Indexed {len(documents)} code chunks")
    else:
        print("No documents found to index")


def index_logs(model: SentenceTransformer, client: chromadb.Client, hours: int = 24):
    """Index recent system logs."""
    collection = client.get_or_create_collection(
        name=COLLECTION_LOGS,
        metadata={"description": "System logs"}
    )

    # Clear existing
    existing = collection.get()
    if existing['ids']:
        collection.delete(ids=existing['ids'])

    documents = []
    metadatas = []
    ids = []

    # Get journalctl logs
    since = datetime.now() - timedelta(hours=hours)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    try:
        result = subprocess.run(
            ['journalctl', '--since', since_str, '--no-pager', '-q'],
            capture_output=True, text=True, timeout=30
        )
        logs = result.stdout

        if logs:
            # Split into chunks by time periods
            lines = logs.strip().split('\n')
            chunk_lines = []
            current_chunk = []

            for line in lines:
                current_chunk.append(line)
                if len(current_chunk) >= 50:  # ~50 lines per chunk
                    chunk_lines.append('\n'.join(current_chunk))
                    current_chunk = []

            if current_chunk:
                chunk_lines.append('\n'.join(current_chunk))

            for i, chunk in enumerate(chunk_lines):
                documents.append(chunk)
                metadatas.append({
                    "source": "journalctl",
                    "type": "log",
                    "hours": hours,
                    "chunk": i
                })
                ids.append(f"journal_{i}")

            print(f"  Parsed {len(chunk_lines)} log chunks from journalctl")
    except Exception as e:
        print(f"  Error reading journalctl: {e}", file=sys.stderr)

    # Also try auth.log if readable
    auth_log = Path('/var/log/auth.log')
    if auth_log.exists():
        try:
            content = auth_log.read_text(errors='ignore')
            lines = content.strip().split('\n')[-500:]  # Last 500 lines
            chunks = chunk_text('\n'.join(lines), chunk_size=300)

            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({
                    "source": "auth.log",
                    "type": "log",
                    "chunk": i
                })
                ids.append(f"auth_{i}")

            print(f"  Parsed {len(chunks)} chunks from auth.log")
        except PermissionError:
            print("  Skipping auth.log (permission denied)")
        except Exception as e:
            print(f"  Error reading auth.log: {e}", file=sys.stderr)

    if documents:
        print(f"Generating embeddings for {len(documents)} log chunks...")
        embeddings = model.encode(documents, show_progress_bar=True).tolist()
        collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Indexed {len(documents)} log chunks")
    else:
        print("No logs found to index")


def chunk_by_section(text: str, filename: str) -> list[tuple[str, str]]:
    """Split markdown/text by ## headers. Returns list of (section_title, content)."""
    sections = []
    current_title = filename
    current_lines = []

    for line in text.split('\n'):
        if line.startswith('## '):
            # Save previous section
            if current_lines:
                body = '\n'.join(current_lines).strip()
                if body:
                    sections.append((current_title, body))
            current_title = line.lstrip('#').strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Save last section
    if current_lines:
        body = '\n'.join(current_lines).strip()
        if body:
            sections.append((current_title, body))

    # If no ## headers found, fall back to word-based chunking
    if len(sections) <= 1 and len(text.split()) > 500:
        chunks = chunk_text(text, chunk_size=300)
        return [(filename, c) for c in chunks]

    return sections


def index_docs(model: SentenceTransformer, client: chromadb.Client, paths: list[str] = None):
    """Index medical/first-aid documents (.txt, .md, .html files)."""
    collection = client.get_or_create_collection(
        name=COLLECTION_DOCS,
        metadata={"description": "Medical and first-aid documents"}
    )

    # Clear existing
    existing = collection.get()
    if existing['ids']:
        collection.delete(ids=existing['ids'])

    search_paths = [Path(p) for p in paths] if paths else [DOCS_DIR]
    extensions = {'.txt', '.md', '.html', '.htm'}

    documents = []
    metadatas = []
    ids = []

    for search_path in search_paths:
        if not search_path.exists():
            print(f"  Skipping {search_path} (not found)")
            continue

        if search_path.is_file():
            files = [search_path]
        else:
            files = sorted(search_path.rglob('*'))

        for f in files:
            if not f.is_file() or f.suffix.lower() not in extensions:
                continue
            try:
                content = f.read_text(errors='ignore')
                if len(content.strip()) < 20:
                    continue

                # Strip HTML tags if needed
                if f.suffix.lower() in ('.html', '.htm'):
                    content = re.sub(r'<[^>]+>', ' ', content)
                    content = re.sub(r'\s+', ' ', content).strip()

                # Use relative path from docs dir for cleaner metadata
                try:
                    rel = f.relative_to(DOCS_DIR)
                except ValueError:
                    rel = f.name

                # Split by section headers for precise retrieval
                sections = chunk_by_section(content, str(rel))

                for i, (title, body) in enumerate(sections):
                    doc_text = f"[{rel}] {title}\n\n{body}"
                    documents.append(doc_text)
                    metadatas.append({
                        "source": str(f),
                        "filename": f.name,
                        "section": title,
                        "category": f.parent.name if f.parent != DOCS_DIR else "general",
                        "type": "docs",
                        "chunk": i
                    })
                    ids.append(f"doc_{rel}_{i}")

                print(f"  Indexed: {rel} ({len(sections)} sections)")
            except Exception as e:
                print(f"  Error reading {f}: {e}", file=sys.stderr)

    if documents:
        print(f"Generating embeddings for {len(documents)} doc chunks...")
        embeddings = model.encode(documents, show_progress_bar=True).tolist()
        collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Indexed {len(documents)} document chunks")
    else:
        print("No documents found. Add .txt or .md files to ~/offline-library/medical/")


def search_wikipedia(query: str, limit: int = 3) -> list[dict]:
    """Search Wikipedia using libzim."""
    results = []

    try:
        from libzim.reader import Archive
        from libzim.search import Query, Searcher

        for zim_path in [WIKIPEDIA_ZIM, WIKIBOOKS_ZIM]:
            if not zim_path.exists():
                continue

            archive = Archive(str(zim_path))
            searcher = Searcher(archive)
            query_obj = Query().set_query(query)
            search = searcher.search(query_obj)

            for i, result in enumerate(search.getResults(0, limit)):
                try:
                    entry = archive.get_entry_by_path(result)
                    item = entry.get_item()
                    content = bytes(item.content).decode('utf-8', errors='ignore')

                    # Strip HTML tags
                    clean = re.sub(r'<[^>]+>', ' ', content)
                    clean = re.sub(r'\s+', ' ', clean).strip()

                    # Limit content length (reduced for Pi 5 memory constraints)
                    if len(clean) > 800:
                        clean = clean[:800] + "..."

                    results.append({
                        "title": entry.title,
                        "content": clean,
                        "source": zim_path.name
                    })
                except Exception as e:
                    continue

    except ImportError:
        print("libzim not available, skipping Wikipedia search", file=sys.stderr)
    except Exception as e:
        print(f"Wikipedia search error: {e}", file=sys.stderr)

    return results


def query_ollama(prompt: str, context: str, max_context_chars: int = 1500) -> str:
    """Query Ollama with context."""
    import requests

    # Truncate context to fit within model limits
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n[... truncated ...]"

    full_prompt = f"""You are a helpful AI assistant for the Cyberboy handheld device.
Use the following context to answer the question. If the context doesn't contain relevant information, say so.

CONTEXT:
{context}

QUESTION: {prompt}

ANSWER:"""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 500
                }
            },
            timeout=300
        )
        response.raise_for_status()
        return response.json()['response']
    except Exception as e:
        return f"Error querying Ollama: {e}"


def query(question: str, sources: list[str] = None, top_k: int = 2, no_llm: bool = False) -> str:
    """Query the RAG system."""
    ensure_dirs()
    model = get_embedding_model()
    client = get_chroma_client()

    if sources is None:
        sources = ['code', 'logs', 'wiki', 'docs']

    context_parts = []

    # Search vector collections
    query_embedding = model.encode([question])[0].tolist()

    for source in sources:
        if source == 'docs':
            try:
                collection = client.get_collection(COLLECTION_DOCS)
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k
                )
                for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                    section = meta.get('section', meta.get('filename', 'unknown'))
                    context_parts.append(f"[MEDICAL - {section}]\n{doc}\n")
            except Exception as e:
                print(f"Docs search error: {e}", file=sys.stderr)

        elif source == 'code':
            try:
                collection = client.get_collection(COLLECTION_CODE)
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k
                )
                for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                    context_parts.append(f"[CODE - {meta.get('filename', 'unknown')}]\n{doc}\n")
            except Exception as e:
                print(f"Code search error: {e}", file=sys.stderr)

        elif source == 'logs':
            try:
                collection = client.get_collection(COLLECTION_LOGS)
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k
                )
                for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                    context_parts.append(f"[LOG - {meta.get('source', 'system')}]\n{doc}\n")
            except Exception as e:
                print(f"Log search error: {e}", file=sys.stderr)

        elif source == 'wiki':
            wiki_results = search_wikipedia(question, limit=3)
            for result in wiki_results:
                context_parts.append(f"[WIKIPEDIA - {result['title']}]\n{result['content']}\n")

    if not context_parts:
        return "No relevant context found. Try indexing first with: cyberrag index"

    context = "\n---\n".join(context_parts)

    if no_llm:
        return f"=== Retrieved Context ===\n\n{context}"

    print("Querying LLM...", file=sys.stderr)
    return query_ollama(question, context)


def interactive_mode():
    """Interactive query mode."""
    print("\n╔══════════════════════════════════════╗")
    print("║         CyberRAG Interactive         ║")
    print("╠══════════════════════════════════════╣")
    print("║ Commands:                            ║")
    print("║   /sources [code,logs,wiki,docs]     ║")
    print("║   /medical - query docs only         ║")
    print("║   /raw - show raw context            ║")
    print("║   /index - reindex all               ║")
    print("║   /quit - exit                       ║")
    print("╚══════════════════════════════════════╝\n")

    sources = ['code', 'logs', 'wiki', 'docs']
    raw_mode = False

    while True:
        try:
            question = input("\n\033[96m>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not question:
            continue

        if question.startswith('/'):
            cmd = question.lower().split()
            if cmd[0] == '/quit' or cmd[0] == '/exit':
                break
            elif cmd[0] == '/sources':
                if len(cmd) > 1:
                    sources = cmd[1].split(',')
                print(f"Sources: {sources}")
            elif cmd[0] == '/raw':
                raw_mode = not raw_mode
                print(f"Raw mode: {raw_mode}")
            elif cmd[0] == '/medical':
                sources = ['docs', 'wiki']
                print("Sources: docs,wiki (medical mode)")
            elif cmd[0] == '/index':
                print("Reindexing...")
                model = get_embedding_model()
                client = get_chroma_client()
                index_code(model, client)
                index_logs(model, client)
                index_docs(model, client)
            else:
                print("Unknown command")
            continue

        result = query(question, sources=sources, no_llm=raw_mode)
        print(f"\n\033[93m{result}\033[0m")


def main():
    parser = argparse.ArgumentParser(
        description="CyberRAG - Local RAG system for Cyberboy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cyberrag index                    # Index code, logs, and docs
  cyberrag index --only docs        # Index only medical docs
  cyberrag index --code-path ~/my   # Index custom path
  cyberrag query "how does voice input work?"
  cyberrag query "what errors in logs?" --sources logs
  cyberrag query "what is SDR?" --sources wiki
  cyberrag query "how to treat a burn?" --sources docs
  cyberrag interactive              # Interactive mode (/medical for docs-only)
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Index command
    index_parser = subparsers.add_parser('index', help='Index documents')
    index_parser.add_argument('--code-path', nargs='+', help='Paths to index for code')
    index_parser.add_argument('--log-hours', type=int, default=24, help='Hours of logs to index')
    index_parser.add_argument('--docs-path', nargs='+', help='Paths to index for medical docs')
    index_parser.add_argument('--only', choices=['code', 'logs', 'docs'], help='Only index specific type')

    # Query command
    query_parser = subparsers.add_parser('query', aliases=['q'], help='Query the RAG system')
    query_parser.add_argument('question', nargs='+', help='Question to ask')
    query_parser.add_argument('--sources', '-s', default='code,logs,wiki,docs', help='Sources to search (comma-separated: code,logs,wiki,docs)')
    query_parser.add_argument('--top-k', '-k', type=int, default=2, help='Number of results per source')
    query_parser.add_argument('--raw', '-r', action='store_true', help='Show raw context without LLM')

    # Interactive command
    subparsers.add_parser('interactive', aliases=['i'], help='Interactive mode')

    # Status command
    subparsers.add_parser('status', help='Show index status')

    args = parser.parse_args()

    ensure_dirs()

    if args.command == 'index':
        model = get_embedding_model()
        client = get_chroma_client()

        if args.only is None or args.only == 'code':
            print("\n=== Indexing Code ===")
            index_code(model, client, args.code_path)

        if args.only is None or args.only == 'logs':
            print("\n=== Indexing Logs ===")
            index_logs(model, client, args.log_hours)

        if args.only is None or args.only == 'docs':
            print("\n=== Indexing Medical Docs ===")
            index_docs(model, client, args.docs_path)

        print("\nIndexing complete!")

    elif args.command in ('query', 'q'):
        question = ' '.join(args.question)
        sources = args.sources.split(',')
        result = query(question, sources=sources, top_k=args.top_k, no_llm=args.raw)
        print(result)

    elif args.command in ('interactive', 'i'):
        interactive_mode()

    elif args.command == 'status':
        client = get_chroma_client()
        print("\n=== CyberRAG Status ===\n")

        for name in [COLLECTION_CODE, COLLECTION_LOGS, COLLECTION_DOCS]:
            try:
                collection = client.get_collection(name)
                count = collection.count()
                print(f"{name}: {count} chunks indexed")
            except:
                print(f"{name}: not indexed")

        print(f"\nWikipedia ZIM: {'✓' if WIKIPEDIA_ZIM.exists() else '✗'}")
        print(f"Wikibooks ZIM: {'✓' if WIKIBOOKS_ZIM.exists() else '✗'}")
        print(f"Medical docs dir: {'✓' if DOCS_DIR.exists() else '✗'} ({DOCS_DIR})")
        if DOCS_DIR.exists():
            doc_files = list(DOCS_DIR.rglob('*'))
            doc_files = [f for f in doc_files if f.is_file()]
            total_size = sum(f.stat().st_size for f in doc_files)
            print(f"  {len(doc_files)} files, {total_size / 1024 / 1024:.1f} MB")
        print(f"\nData directory: {DATA_DIR}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
