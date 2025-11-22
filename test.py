# llama_index_chunk_test.py

import os
from llama_index.core import SimpleDirectoryReader, Settings, Document
from llama_index.core.node_parser import SentenceSplitter

# ---------------------------------------
# 1) Load your dataset files
# ---------------------------------------

file_paths = [
    "dataset/faq_data.csv",
    "dataset/Flipkart-1.pdf",
    "dataset/Flipkart-2.pdf"
]

documents = []

# Use SimpleDirectoryReader on specific files
reader = SimpleDirectoryReader(input_files=file_paths)
documents = reader.load_data()

print(f"📄 Loaded raw documents: {len(documents)}")


# ---------------------------------------
# 2) Apply LlamaIndex Chunking
# ---------------------------------------

Settings.text_splitter = SentenceSplitter(
    chunk_size=500,
    chunk_overlap=50
)

chunks = Settings.text_splitter.get_nodes_from_documents(documents)

print(f"🔹 Total LlamaIndex Chunks: {len(chunks)}")

# ---------------------------------------
# 3) Optional: Print stats
# ---------------------------------------

lengths = [len(node.get_content()) for node in chunks]

print("\n📊 Chunk Length Statistics")
print(f"Min length: {min(lengths)}")
print(f"Max length: {max(lengths)}")
print(f"Avg length: {sum(lengths) // len(lengths)}")

# ---------------------------------------
# 4) Optional: Preview first chunk
# ---------------------------------------

print("\n📝 Sample Chunk #1:")
print(chunks[0].get_content())
