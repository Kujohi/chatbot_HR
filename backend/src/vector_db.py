import getpass
import os

from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
load_dotenv()

if not os.getenv("PINECONE_API_KEY"):
    os.environ["PINECONE_API_KEY"] = getpass.getpass("Enter your Pinecone API key: ")

pinecone_api_key = os.environ.get("PINECONE_API_KEY")

pc = Pinecone(api_key=pinecone_api_key)


index_name = "test-index"  # change if desired

if not pc.has_index(index_name):
    pc.create_index(
        name=index_name,
        dimension=3072,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )

index = pc.Index(index_name)
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")
vector_store = PineconeVectorStore(index=index, embedding=embeddings)

prompt = "Các yêu cầu đối với vị trí chuyên viên tuyển dụng tại công ty Menas là gì?"

result = vector_store.similarity_search(prompt, filter={'isDocument': True})
print(result)