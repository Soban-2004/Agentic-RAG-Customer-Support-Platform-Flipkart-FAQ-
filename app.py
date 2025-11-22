import os
import chainlit as cl
from dotenv import load_dotenv
import qdrant_client

# LlamaIndex Imports
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.groq import Groq
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.callbacks import CallbackManager

# Chainlit Callback Handler
from chainlit.llama_index.callbacks import LlamaIndexCallbackHandler

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
CHATGROQ_API_KEY = os.getenv("CHATGROQ_API_KEY")
COLLECTION_NAME = "flipkart_faqs"

if not QDRANT_API_KEY or not QDRANT_URL or not CHATGROQ_API_KEY:
    raise ValueError("❌ Missing API Keys. Please check your .env file.")

# --- 1. GLOBAL SETTINGS ---
Settings.embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

Settings.llm = Groq(
    model="llama-3.1-8b-instant", 
    api_key=CHATGROQ_API_KEY
)

@cl.on_chat_start
async def start():
    """
    Runs when a new chat session starts.
    Initializes Async Qdrant Client and Chat Engine.
    """
    
    # 1. Setup Chainlit Callbacks
    cl_callback = LlamaIndexCallbackHandler()
    Settings.callback_manager = CallbackManager([cl_callback])

    # 2. Connect to Qdrant (Async Fix)
    try:
        # Synchronous client (for metadata/management)
        client = qdrant_client.QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
        )
        
        # Asynchronous client (for async queries in Chainlit)
        aclient = qdrant_client.AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
        )
        
        vector_store = QdrantVectorStore(
            client=client, 
            aclient=aclient,
            collection_name=COLLECTION_NAME
        )
        
        # Load Index
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
        
    except Exception as e:
        await cl.Message(content=f"❌ Error connecting to Qdrant: {e}").send()
        return

    # 3. Configure Chat Engine
    system_prompt = (
        "You are a helpful Flipkart customer support assistant. "
        "Use the provided context to answer the question in detail. "
        "Keep your answer **under 200 words**. "
        "If relevant, provide step-by-step guidance or examples. "
        "Do not just give one sentence unless the question is very simple."
    )
    
    memory = ChatMemoryBuffer.from_defaults(token_limit=4000)
    
    # Create the engine
    chat_engine = index.as_chat_engine(
        chat_mode="context",
        memory=memory,
        system_prompt=system_prompt,
        streaming=True
    )

    # 4. Store engine in session
    cl.user_session.set("chat_engine", chat_engine)

    # 5. Send Welcome Message with Centered Title
    await cl.Message(
        content="""# 🛍️ Flipkart Customer Chatbot

👋 **Hello!** How can I help you with your shopping today? Ask me about:
* 📦 Order Tracking
* 💸 Refunds & Returns
* 💳 Payments & EMI""",
        author="Flipkart Support"
    ).send()


@cl.on_message
async def main(message: cl.Message):
    """
    Runs on every user message.
    """
    chat_engine = cl.user_session.get("chat_engine")
    
    if not chat_engine:
        await cl.Message(content="⚠️ Chat engine not initialized. Please refresh.").send()
        return

    # Set the author to match
    msg = cl.Message(content="", author="Flipkart Support")

    # Generate streaming response using the async engine
    response = await chat_engine.astream_chat(message.content)

    async for token in response.async_response_gen():
        await msg.stream_token(token)

    await msg.send()