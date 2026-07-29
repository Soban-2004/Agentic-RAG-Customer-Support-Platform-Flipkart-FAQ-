"""
Ingestion pipeline: chunk the FAQ/PDF dataset, embed it (dense + BM25 sparse),
and upsert into Qdrant with hybrid search enabled.

Idempotent by default: each chunk's point ID is a deterministic hash of its
own text (uuid5), so re-running this script after a content change only
touches the chunks that actually changed -- no delete-and-rebuild needed. Use
--reset for a one-time full rebuild (e.g. after changing the embedding model,
chunk size, or -- as when hybrid search was first added -- the collection's
vector schema itself).
"""

import argparse
import hashlib
import os
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Windows terminals often default to a non-UTF-8 codepage (cp1252), which
# can't encode the emoji in this script's progress prints.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

# LlamaIndex Imports
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    Settings,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.qdrant import QdrantVectorStore

from src.common.embed_factory import build_embed_model
from src.common.qdrant_factory import get_sync_qdrant_client, is_remote

# Setup logging to see progress
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

# 1) Load Environment Variables
load_dotenv()

COLLECTION_NAME = "flipkart_faqs"
# BM25-style sparse embedding for hybrid (dense + sparse) search -- must match
# the fastembed_sparse_model used at query time in src/agent/chat_agent.py.
SPARSE_MODEL = "Qdrant/bm25"


def _source_type(file_name: str) -> str:
    """Coarse metadata tag for future filtered retrieval (e.g. prefer FAQ
    entries over policy PDF boilerplate for certain query types)."""
    return "faq" if file_name.lower().endswith(".csv") else "policy_doc"


def _deterministic_id(text: str) -> str:
    """Same chunk text -> same Qdrant point ID, so re-ingesting unchanged
    content upserts in place instead of creating a duplicate point."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, text))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate the collection first, instead of incremental upsert.",
    )
    args = parser.parse_args()

    print("Configuring settings...")
    # Embedding model -- must match main.py's query-time embed model exactly,
    # or retrieval silently degrades (ingestion used to use a different model
    # here). build_embed_model() is shared with main.py for exactly this
    # reason -- see src/common/embed_factory.py.
    Settings.embed_model = build_embed_model()
    Settings.text_splitter = SentenceSplitter(chunk_size=500, chunk_overlap=50)

    # NOTE: local/embedded mode only allows ONE open client per storage folder --
    # stop the running Chainlit app before running this script. See
    # src/common/qdrant_factory.py for details.
    print(f"Connecting to Qdrant ({'remote' if is_remote() else 'local embedded'})...")
    client = get_sync_qdrant_client(timeout=60)

    if args.reset and client.collection_exists(COLLECTION_NAME):
        print(f"--reset passed: deleting existing collection '{COLLECTION_NAME}'...")
        client.delete_collection(COLLECTION_NAME)

    print("Loading documents...")
    DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "dataset"
    file_paths = [
        str(DATA_DIR / "faq_data.csv"),
        str(DATA_DIR / "Flipkart-1.pdf"),
        str(DATA_DIR / "Flipkart-2.pdf"),
    ]
    valid_files = [f for f in file_paths if os.path.exists(f)]
    if not valid_files:
        raise FileNotFoundError("No valid files found in the dataset folder.")

    documents = SimpleDirectoryReader(input_files=valid_files).load_data()
    print(f"Loaded {len(documents)} raw documents.")

    for doc in documents:
        doc.metadata["source_type"] = _source_type(doc.metadata.get("file_name", ""))

    nodes = Settings.text_splitter.get_nodes_from_documents(documents)
    for node in nodes:
        node.id_ = _deterministic_id(node.get_content())
    content_hash = hashlib.sha256(
        "".join(sorted(n.id_ for n in nodes)).encode()
    ).hexdigest()[:12]
    print(f"Total chunks: {len(nodes)} (content fingerprint: {content_hash})")

    # QdrantVectorStore manages collection creation itself when hybrid is enabled --
    # it needs named dense + sparse vectors, a schema the old manual
    # client.create_collection() call (dense-only) didn't set up.
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        enable_hybrid=True,
        fastembed_sparse_model=SPARSE_MODEL,
        batch_size=64,
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print("Generating dense + sparse embeddings and upserting to Qdrant...")
    VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
        show_progress=True,
    )

    print("Indexing complete! Collection ready.")


if __name__ == "__main__":
    main()
