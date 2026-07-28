#!/usr/bin/env python3
"""
CyberRAG - Local RAG system for Cyberboy
Indexes Wikipedia, logs, and custom code for AI-powered queries
Supports Ollama (local/offline) and Claude CLI (online) as LLM engines
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
OLLAMA_MODEL = "gemma3:1b"
OLLAMA_URL = "http://localhost:11434"
# How long Ollama keeps the model resident in RAM after a query.
# RAM-only (no idle CPU/battery cost); "0" unloads immediately to free memory.
OLLAMA_KEEP_ALIVE = "5m"

# Engine config
ENGINE_OLLAMA = "ollama"
ENGINE_CLAUDE = "claude"
DEFAULT_ENGINE = ENGINE_OLLAMA
CLAUDE_CLI = HOME / ".local" / "bin" / "claude"

# System prompts
GENERIC_SYSTEM_PROMPT = """You are a helpful AI assistant for the Cyberboy handheld device.
Use the following context to answer the question. If the context doesn't contain relevant information, say so."""

MEDICAL_SYSTEM_PROMPT = """You are a medical information assistant running on a portable device. You help users understand possible causes of their symptoms based on medical reference material.

CRITICAL RULES:
1. You are NOT a doctor. You CANNOT diagnose. Always state this clearly.
2. Base your answers ONLY on the provided reference material. If the references don't cover the topic, say so.
3. List possible conditions with brief explanations, ordered by how commonly they match the described symptoms.
4. Always recommend consulting a healthcare professional for proper diagnosis.
5. For any symptoms suggesting emergency (chest pain, difficulty breathing, sudden severe headache, signs of stroke), lead with "SEEK IMMEDIATE MEDICAL ATTENTION" before any other information.
6. Be concise. Do not ramble.
7. Never invent medical facts. If unsure, say "I don't have enough information in my references to answer this.\""""

MEDICAL_DISCLAIMER = (
    "\n\n---\n"
    "NOT MEDICAL ADVICE. For informational purposes only. "
    "Always consult a qualified healthcare professional for diagnosis and treatment."
)

EMERGENCY_KEYWORDS = [
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "shortness of breath", "choking", "unconscious", "not breathing",
    "severe bleeding", "stroke", "seizure", "heart attack", "anaphylaxis",
    "overdose", "poisoning", "drowning", "suicidal", "suicide",
    "not responsive", "collapsed", "no pulse",
]


def check_emergency(query_text: str) -> Optional[str]:
    """Check if the query describes an emergency situation."""
    query_lower = query_text.lower()
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in query_lower:
            return (
                "!! EMERGENCY WARNING: If this is a real emergency, "
                "call your local emergency number (911, 112, 999) IMMEDIATELY. "
                "The information below is for reference only.\n\n"
            )
    return None


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


def _clean_wiki_html(content: str) -> str:
    """Strip MediaWiki cruft so the LLM sees prose, not CSS."""
    # Drop entire <style>/<script>/<noscript> blocks (contents and tags).
    content = re.sub(r'<(style|script|noscript)\b[^>]*>.*?</\1>',
                     ' ', content, flags=re.DOTALL | re.IGNORECASE)
    # Drop HTML comments and CSS-like /* ... */ block comments.
    content = re.sub(r'<!--.*?-->', ' ', content, flags=re.DOTALL)
    content = re.sub(r'/\*.*?\*/', ' ', content, flags=re.DOTALL)
    # Now strip remaining tags.
    content = re.sub(r'<[^>]+>', ' ', content)
    # Decode a few common entities and collapse whitespace.
    content = (content.replace('&nbsp;', ' ')
                      .replace('&amp;', '&')
                      .replace('&lt;', '<')
                      .replace('&gt;', '>')
                      .replace('&quot;', '"')
                      .replace('&#39;', "'"))
    content = re.sub(r'\s+', ' ', content).strip()
    return content


def _wiki_entity_candidates(query: str) -> list[str]:
    """Guess article titles to try by direct path lookup."""
    stop = {
        'how', 'many', 'much', 'what', 'where', 'when', 'who', 'why', 'is',
        'are', 'was', 'were', 'do', 'does', 'did', 'the', 'a', 'an', 'of',
        'in', 'on', 'at', 'to', 'for', 'and', 'or', 'people', 'live', 'lives',
        'population', 'tell', 'me', 'about', 'explain', 'describe',
    }
    cleaned = re.sub(r'[^\w\s-]', ' ', query)
    words = [w for w in cleaned.split() if w]
    content_words = [w for w in words if w.lower() not in stop]
    candidates: list[str] = []
    if content_words:
        candidates.append(' '.join(w.capitalize() for w in content_words))
        # Last content word alone (often the entity, e.g. "greece")
        candidates.append(content_words[-1].capitalize())
    # De-dup, preserve order
    seen = set()
    out = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def search_wikipedia(query: str, limit: int = 3) -> list[dict]:
    """Search Wikipedia using libzim. Tries direct article lookup first."""
    results = []
    seen_paths = set()

    try:
        from libzim.reader import Archive
        from libzim.search import Query, Searcher

        for zim_path in [WIKIPEDIA_ZIM, WIKIBOOKS_ZIM]:
            if not zim_path.exists():
                continue

            archive = Archive(str(zim_path))

            # 1) Try direct article-path lookup for entity-like queries.
            for candidate in _wiki_entity_candidates(query):
                path = candidate.replace(' ', '_')
                try:
                    entry = archive.get_entry_by_path(f"A/{path}")
                except Exception:
                    try:
                        entry = archive.get_entry_by_path(path)
                    except Exception:
                        continue
                # Follow redirects
                try:
                    if entry.is_redirect:
                        entry = entry.get_redirect_entry()
                except Exception:
                    pass
                key = (zim_path.name, entry.path)
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                try:
                    item = entry.get_item()
                    content = bytes(item.content).decode('utf-8', errors='ignore')
                    clean = _clean_wiki_html(content)
                    if len(clean) < 100:
                        continue
                    if len(clean) > 2000:
                        clean = clean[:2000] + "..."
                    results.append({
                        "title": entry.title,
                        "content": clean,
                        "source": zim_path.name,
                    })
                    break  # one direct hit per ZIM is enough
                except Exception:
                    continue

            # 2) Full-text search to fill remaining slots.
            try:
                searcher = Searcher(archive)
                query_obj = Query().set_query(query)
                search = searcher.search(query_obj)
                ft_results = list(search.getResults(0, limit + 3))
            except Exception as e:
                print(f"Wikipedia FT search error ({zim_path.name}): {e}",
                      file=sys.stderr)
                ft_results = []

            for result in ft_results:
                if len([r for r in results if r['source'] == zim_path.name]) >= limit:
                    break
                key = (zim_path.name, result)
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                try:
                    entry = archive.get_entry_by_path(result)
                    item = entry.get_item()
                    content = bytes(item.content).decode('utf-8', errors='ignore')
                    clean = _clean_wiki_html(content)
                    if len(clean) < 100:
                        continue
                    if len(clean) > 2000:
                        clean = clean[:2000] + "..."
                    results.append({
                        "title": entry.title,
                        "content": clean,
                        "source": zim_path.name,
                    })
                except Exception:
                    continue

    except ImportError:
        print("libzim not available, skipping Wikipedia search", file=sys.stderr)
    except Exception as e:
        print(f"Wikipedia search error: {e}", file=sys.stderr)

    return results


def query_ollama(prompt: str, context: str, system_prompt: str = None,
                 max_context_chars: int = 1500) -> str:
    """Query Ollama with context."""
    import requests

    if system_prompt is None:
        system_prompt = GENERIC_SYSTEM_PROMPT

    # Truncate context to fit within model limits
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n[... truncated ...]"

    full_prompt = f"""{system_prompt}

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
                "keep_alive": OLLAMA_KEEP_ALIVE,
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


def query_claude(prompt: str, context: str, system_prompt: str = None,
                 claude_model: str = "sonnet", max_context_chars: int = 6000) -> str:
    """Query Claude CLI with context. Requires internet."""
    if system_prompt is None:
        system_prompt = GENERIC_SYSTEM_PROMPT

    # Claude handles much larger context than local models
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n[... truncated ...]"

    user_message = f"""CONTEXT:
{context}

QUESTION: {prompt}

ANSWER:"""

    cmd = [
        str(CLAUDE_CLI), "-p",
        "--no-session-persistence",
        "--model", claude_model,
        "--system-prompt", system_prompt,
    ]

    try:
        result = subprocess.run(
            cmd,
            input=user_message,
            capture_output=True,
            text=True,
            timeout=180
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "network" in stderr.lower() or "connect" in stderr.lower():
                return "Error: No internet connection. Use local engine (--engine ollama) for offline queries."
            return f"Error from Claude: {stderr}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Error: Claude timed out (180s). Try a shorter query or use --engine ollama."
    except FileNotFoundError:
        return "Error: Claude CLI not found at ~/.local/bin/claude. Use --engine ollama instead."


def query(question: str, sources: list[str] = None, top_k: int = 2,
          no_llm: bool = False, engine: str = None, medical: bool = False,
          claude_model: str = "sonnet") -> str:
    """Query the RAG system."""
    ensure_dirs()
    model = get_embedding_model()
    client = get_chroma_client()

    if engine is None:
        engine = DEFAULT_ENGINE

    # Medical mode defaults to docs + wiki sources
    if medical and sources is None:
        sources = ['docs', 'wiki']
    elif sources is None:
        sources = ['code', 'logs', 'wiki', 'docs']

    # Medical mode uses more results for better coverage
    if medical and top_k < 3:
        top_k = 3

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

    # Select system prompt
    sys_prompt = MEDICAL_SYSTEM_PROMPT if medical else None

    # Check for emergency keywords in medical mode
    emergency_warning = ""
    if medical:
        emergency_warning = check_emergency(question) or ""

    # Query the selected engine
    engine_label = f"Claude ({claude_model})" if engine == ENGINE_CLAUDE else f"Ollama ({OLLAMA_MODEL})"
    print(f"Querying {engine_label}...", file=sys.stderr)

    if engine == ENGINE_CLAUDE:
        response = query_claude(question, context, system_prompt=sys_prompt,
                                claude_model=claude_model)
    else:
        response = query_ollama(question, context, system_prompt=sys_prompt)

    # Assemble final response
    result = emergency_warning + response
    if medical:
        result += MEDICAL_DISCLAIMER

    return result


def interactive_mode():
    """Interactive query mode."""
    print("\n╔══════════════════════════════════════╗")
    print("║         CyberRAG Interactive         ║")
    print("╠══════════════════════════════════════╣")
    print("║ Commands:                            ║")
    print("║   /sources [code,logs,wiki,docs]     ║")
    print("║   /medical  - medical mode (toggle)  ║")
    print("║   /claude   - use Claude (online)    ║")
    print("║   /local    - use Ollama (offline)   ║")
    print("║   /model X  - claude model           ║")
    print("║              (sonnet/haiku/opus)      ║")
    print("║   /raw      - show raw context       ║")
    print("║   /engine   - show current engine    ║")
    print("║   /index    - reindex all            ║")
    print("║   /quit     - exit                   ║")
    print("╚══════════════════════════════════════╝\n")

    sources = ['code', 'logs', 'wiki', 'docs']
    raw_mode = False
    engine = DEFAULT_ENGINE
    medical_mode = False
    claude_model = "sonnet"

    while True:
        # Build prompt indicator
        mode_tag = ""
        if medical_mode:
            mode_tag += "\033[91m[MED]\033[0m "
        if engine == ENGINE_CLAUDE:
            mode_tag += "\033[95m[claude]\033[0m "
        else:
            mode_tag += "\033[92m[local]\033[0m "

        try:
            question = input(f"\n{mode_tag}\033[96m>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not question:
            continue

        if question.startswith('/'):
            cmd = question.lower().split()
            if cmd[0] in ('/quit', '/exit'):
                break
            elif cmd[0] == '/sources':
                if len(cmd) > 1:
                    sources = cmd[1].split(',')
                print(f"Sources: {sources}")
            elif cmd[0] == '/raw':
                raw_mode = not raw_mode
                print(f"Raw mode: {raw_mode}")
            elif cmd[0] == '/medical':
                medical_mode = not medical_mode
                if medical_mode:
                    sources = ['docs', 'wiki']
                    print("Medical mode ON (sources: docs,wiki)")
                else:
                    sources = ['code', 'logs', 'wiki', 'docs']
                    print("Medical mode OFF (sources: all)")
            elif cmd[0] == '/claude':
                engine = ENGINE_CLAUDE
                print(f"Engine: Claude ({claude_model}) - requires internet")
            elif cmd[0] == '/local':
                engine = ENGINE_OLLAMA
                print(f"Engine: Ollama ({OLLAMA_MODEL}) - offline")
            elif cmd[0] == '/model':
                if len(cmd) > 1 and cmd[1] in ('sonnet', 'haiku', 'opus'):
                    claude_model = cmd[1]
                    print(f"Claude model: {claude_model}")
                else:
                    print("Usage: /model sonnet|haiku|opus")
            elif cmd[0] == '/engine':
                if engine == ENGINE_CLAUDE:
                    print(f"Engine: Claude ({claude_model})")
                else:
                    print(f"Engine: Ollama ({OLLAMA_MODEL})")
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

        result = query(question, sources=sources, no_llm=raw_mode,
                       engine=engine, medical=medical_mode,
                       claude_model=claude_model)
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
  cyberrag query --engine claude "explain this error"
  cyberrag medical "chest pain when breathing"
  cyberrag medical --engine claude "symptoms of diabetes"
  cyberrag interactive              # Interactive mode
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
    query_parser.add_argument('--engine', '-e', choices=[ENGINE_OLLAMA, ENGINE_CLAUDE], default=DEFAULT_ENGINE, help='LLM engine (default: ollama)')
    query_parser.add_argument('--claude-model', default='sonnet', choices=['sonnet', 'haiku', 'opus'], help='Claude model (default: sonnet)')
    query_parser.add_argument('--medical', '-m', action='store_true', help='Use medical mode (medical prompt + disclaimer)')

    # Medical command (shortcut for query --medical --sources docs,wiki)
    medical_parser = subparsers.add_parser('medical', aliases=['med'], help='Medical query (docs+wiki, medical prompt)')
    medical_parser.add_argument('question', nargs='+', help='Medical question or symptoms')
    medical_parser.add_argument('--top-k', '-k', type=int, default=3, help='Number of results per source')
    medical_parser.add_argument('--raw', '-r', action='store_true', help='Show raw context without LLM')
    medical_parser.add_argument('--engine', '-e', choices=[ENGINE_OLLAMA, ENGINE_CLAUDE], default=DEFAULT_ENGINE, help='LLM engine (default: ollama)')
    medical_parser.add_argument('--claude-model', default='sonnet', choices=['sonnet', 'haiku', 'opus'], help='Claude model (default: sonnet)')

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
        result = query(question, sources=sources, top_k=args.top_k,
                       no_llm=args.raw, engine=args.engine,
                       medical=args.medical, claude_model=args.claude_model)
        print(result)

    elif args.command in ('medical', 'med'):
        question = ' '.join(args.question)
        result = query(question, sources=['docs', 'wiki'], top_k=args.top_k,
                       no_llm=args.raw, engine=args.engine,
                       medical=True, claude_model=args.claude_model)
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

        # Engine info
        print(f"\nDefault engine: {DEFAULT_ENGINE}")
        print(f"Ollama model: {OLLAMA_MODEL}")
        claude_available = CLAUDE_CLI.exists()
        print(f"Claude CLI: {'available' if claude_available else 'not found'} ({CLAUDE_CLI})")

        print(f"\nWikipedia ZIM: {'available' if WIKIPEDIA_ZIM.exists() else 'not found'}")
        print(f"Wikibooks ZIM: {'available' if WIKIBOOKS_ZIM.exists() else 'not found'}")
        print(f"Medical docs dir: {'available' if DOCS_DIR.exists() else 'not found'} ({DOCS_DIR})")
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
