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

from uuid import uuid4

from langchain_core.documents import Document

document_1 = Document(
    page_content="Nhân viên phải check-in trước 8h30 sáng mỗi ngày làm việc.",
    metadata={"source": "quy_dinh"},
)

document_2 = Document(
    page_content="Tất cả nhân viên cần mặc đồng phục công ty vào thứ Hai và thứ Sáu.",
    metadata={"source": "quy_dinh"},
)

document_3 = Document(
    page_content="Không được chia sẻ thông tin nội bộ của công ty cho bên thứ ba.",
    metadata={"source": "quy_dinh"},
)

document_4 = Document(
    page_content="Nhân viên phải hoàn thành báo cáo công việc trước 17h chiều thứ Sáu hàng tuần.",
    metadata={"source": "quy_dinh"},
)

document_5 = Document(
    page_content="Cấm sử dụng thiết bị công ty cho mục đích cá nhân không liên quan đến công việc.",
    metadata={"source": "quy_dinh"},
)

document_6 = Document(
    page_content="Mọi yêu cầu nghỉ phép cần được gửi và phê duyệt trước ít nhất 3 ngày.",
    metadata={"source": "quy_dinh"},
)

document_7 = Document(
    page_content="Nhân viên cần tuân thủ các quy định về bảo mật mật khẩu và tài khoản hệ thống.",
    metadata={"source": "quy_dinh"},
)

document_8 = Document(
    page_content="Không hút thuốc trong khu vực văn phòng và khu vực làm việc chung.",
    metadata={"source": "quy_dinh"},
)

document_9 = Document(
    page_content="Các cuộc họp nội bộ phải được tham gia đầy đủ và đúng giờ.",
    metadata={"source": "quy_dinh"},
)

document_10 = Document(
    page_content="Nhân viên cần giữ gìn vệ sinh chung và bảo quản tài sản công ty.",
    metadata={"source": "quy_dinh"},
)

documents = [
    document_1,
    document_2,
    document_3,
    document_4,
    document_5,
    document_6,
    document_7,
    document_8,
    document_9,
    document_10,
]

uuids = [str(uuid4()) for _ in range(len(documents))]

vector_store.add_documents(documents=documents, ids=uuids)