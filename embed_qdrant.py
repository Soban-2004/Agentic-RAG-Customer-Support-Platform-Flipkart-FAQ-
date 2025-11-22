import os
import logging
import sys
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# LlamaIndex Imports
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    Settings,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore

# Setup logging to see progress
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

# 1) Load Environment Variables
load_dotenv()

QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = "flipkart_faqs"

if not QDRANT_API_KEY or not QDRANT_URL:
    raise ValueError("Please set QDRANT_API_KEY and QDRANT_URL in your .env file")

# 2) Configure Global Settings (Embedding & Chunking)
print("⚙️ Configuring Settings...")

# Embedding Model (Same as your original: all-MiniLM-L6-v2)
Settings.embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Chunking (Same as your original: 500 chars, 50 overlap)
Settings.text_splitter = SentenceSplitter(
    chunk_size=500, 
    chunk_overlap=50
)



# 3) Initialize Qdrant Client
print("🔌 Connecting to Qdrant...")
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
    timeout=60  # Increased timeout
)

# 4) Reset Collection (Optional: Clean slate)
if client.collection_exists(COLLECTION_NAME):
    print(f"🗑️ Collection '{COLLECTION_NAME}' exists. Deleting...")
    client.delete_collection(COLLECTION_NAME)

print(f"Cc Creating collection: {COLLECTION_NAME}")
# Note: LlamaIndex will actually create the collection automatically if it doesn't exist,
# but defining it manually ensures we control the vector size (384 for MiniLM).
client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=qmodels.VectorParams(
        size=384, 
        distance=qmodels.Distance.COSINE
    ),
)

# 5) Load Documents
print("Pg Loading documents...")
file_paths = [
    "dataset/faq_data.csv",
    "dataset/Flipkart-1.pdf",
    "dataset/Flipkart-2.pdf"
]

# Filter only files that actually exist
valid_files = [f for f in file_paths if os.path.exists(f)]

if not valid_files:
    raise FileNotFoundError("No valid files found in the dataset folder.")

# SimpleDirectoryReader can take a list of specific files
documents = SimpleDirectoryReader(input_files=valid_files).load_data()
print(f"✅ Loaded {len(documents)} raw documents.")
nodes = Settings.text_splitter.get_nodes_from_documents(documents)
print("📌 Total LlamaIndex Chunks:", len(nodes))

# 6) Setup Vector Store and Storage Context
vector_store = QdrantVectorStore(
    client=client, 
    collection_name=COLLECTION_NAME,
    # batch_size controls how many nodes are uploaded at once
    batch_size=64 
)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# 7) Create Index (This handles Embedding -> Chunking -> Uploading)
print("🚀 Generating embeddings and uploading to Qdrant (this may take a moment)...")

index = VectorStoreIndex.from_documents(
    documents,
    storage_context=storage_context,
    show_progress=True # Shows a progress bar for the upload
)

print("✅ Indexing complete! Collection ready on Qdrant Cloud.")