# 🤖 Menas HR Bot - Trợ Lý Ảo Nhân Sự Thông Minh (RAG-based)

Dự án **Menas HR Bot** là một hệ thống Trợ lý ảo Nhân sự được xây dựng trên công nghệ **RAG (Retrieval-Augmented Generation)**. Hệ thống giúp tự động hóa việc giải đáp các thắc mắc của nhân viên liên quan đến quy định, chính sách, thủ tục nhân sự của công ty bằng cách truy vấn thông tin trực tiếp từ cơ sở dữ liệu tri thức (tài liệu PDF, hình ảnh chính sách...) được tải lên bởi quản trị viên.

---

## 📌 Phân Mục Tài Liệu
* 📖 [Hướng dẫn Sử dụng chi tiết (User Guide)] - Tài liệu dành cho quản trị viên và người dùng cuối.

---

## 🏛️ Kiến Trúc Hệ Thống (System Architecture)

Hệ thống hoạt động theo mô hình **Client-Server** kết hợp cơ chế **RAG** để cung cấp câu trả lời có tính xác thực cao dựa trên tài liệu nội bộ.

### 🖼️ Sơ Đồ Kiến Trúc Tổng Quan
```
[Chèn sơ đồ kiến trúc hệ thống tổng quan ở đây]
Ví dụ: Sơ đồ tương tác giữa Frontend (Next.js) <-> Backend (FastAPI) <-> Database (Supabase) & VectorDB (Pinecone) & LLM (Gemini API)
```
*(Vui lòng thiết kế hình ảnh sơ đồ kiến trúc và thay thế vào vị trí placeholder trên)*

---

### 🔄 Luồng Hoạt Động (Data Flow) & Kiến Trúc Kỹ Thuật Chi Tiết

Hệ thống triển khai mô hình RAG hai cấp độ (Two-tier Retrieval RAG) kết hợp đa phương thức (Multimodal) nhằm tối ưu hóa việc tìm kiếm trên cả tài liệu văn bản chuẩn (Text-based) và tài liệu quét dạng hình ảnh (Scanned/Image-only PDFs).

---

#### 1. Luồng Đồng bộ & Chỉ mục Tài liệu (SharePoint Sync & Indexing Pipeline)

Quy trình đồng bộ chạy tự động theo chu kỳ (cron job mỗi 5 phút hoặc khi khởi động) để đồng bộ thư mục tài liệu từ **SharePoint Drive** về hệ thống:

```
[SharePoint Drive] ──(Sync 5m)──> [sharepoint_sync_service]
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
        [Kiểm tra & Cập nhật]                            [Đọc file & Phân loại]
        - Khớp sharepoint_item_id                        - Word/PDF văn bản -> Text Document
        - So sánh modified timestamp                     - PDF scan/ảnh -> Image Document
                  │                                               │
                  ▼                                               ▼
         [Cập nhật Supabase]                       [Tạo tóm tắt từ Storage Path]
          (Bảng `documents`)                       (LLM rewrite path -> summary)
                  │                                               │
                  ▼                                               ▼
         [Hủy index cũ nếu có]                     [Nhúng & Lưu Vector Summary]
         (Nếu file bị sửa đổi)                      (isDocument=True -> Pinecone)
                                                                  │
                ┌─────────────────────────────────────────────────┤
                ▼ (Nếu là Text Document)                          ▼ (Nếu là Image Document)
      [Trích xuất & Chunking]                             [Không Chunk nội dung]
      (PyMuPDF / docx loader)                             - Giữ nguyên liên kết file gốc
                │                                         - Chỉ dùng Vector Summary
                ▼                                           để định tuyến (routing)
     [Lưu Chunk Text vào DB]
     (Bảng `document_chunks`)
                │
                ▼
     [Nhúng & Lưu Vector Chunk]
      (chunk_id -> Pinecone)
```

##### Chi tiết các bước xử lý (`sharepoint_sync_service.py` & `document_processing_service.py`):
1. **Quét và Phát hiện Thay đổi**: 
   - Duyệt đệ quy SharePoint Drive thông qua Microsoft Graph API.
   - So sánh `sharepoint_item_id` và timestamp `lastModifiedDateTime` với dữ liệu trong bảng `documents` của Supabase.
   - Nếu tài liệu mới hoặc có thay đổi (`needs_reindex`), hệ thống sẽ tiến hành tải file tạm thời và kích hoạt quy trình chỉ mục. Các file bị xóa trên SharePoint cũng sẽ bị gỡ bỏ tương ứng khỏi Supabase và Pinecone.
2. **Phân loại Tài liệu**:
   - **Tài liệu Văn bản (Text Document)**: Bao gồm các tệp `.docx` và `.pdf` có chứa văn bản có thể trích xuất trực tiếp (sử dụng heuristic kiểm tra nếu có ít nhất một trang chứa trên `MIN_PAGE_TEXT_CHARS = 100` ký tự).
   - **Tài liệu Quét (Image Document)**: Các file `.pdf` dạng scan ảnh (hoặc tệp sơ đồ hệ thống dạng `.drawio.pdf`) không có text thô.
3. **Tạo Vector Định tuyến (Document Summary Routing)**:
   - Dành cho **tất cả** tài liệu: LLM (`gemini-3.1-flash-lite` hoặc tương đương) phân tích đường dẫn thư mục và tên file (ví dụ: `HR/Policies/leave.pdf`) để tạo ra một bản tóm tắt dự đoán nội dung (`rewrite_path_to_summary`).
   - Bản tóm tắt này được nhúng (embedded) bằng `gemini-embedding-2` và lưu vào Pinecone với cờ `isDocument: True` (không chunk). Đây là điểm cốt lõi để định tuyến câu hỏi đến đúng tài liệu ở bước truy vấn.
4. **Xử lý Nội dung chi tiết (Chỉ áp dụng với Tài liệu Văn bản)**:
   - Văn bản được tách từ tệp nhờ `PyMuPDF` (PDF) hoặc `python-docx` (DOCX). Đồng thời tự động sửa đổi một số lỗi font tiếng Việt phổ biến (như chữ `ư`, `Ư`).
   - Chia nhỏ văn bản thành các đoạn (chunks) bằng `RecursiveCharacterTextSplitter` (kích thước chunk 1500 ký tự, overlap 100 ký tự).
   - Lưu trữ văn bản thô của các chunk vào bảng `document_chunks` (Supabase).
   - Nhúng từng chunk thành vector 3072 chiều và đẩy lên Pinecone với metadata đầy đủ (`document_id`, `storage_path`, `chunk_id`, `title`).

---

#### 2. Luồng Truy vấn & Trả lời (Retrieval-Augmented Generation - RAG Pipeline)

Để tối ưu hóa độ chính xác và giảm thiểu việc LLM bị nhiễu bởi các tài liệu không liên quan, hệ thống áp dụng cơ chế truy vấn 2 bước (Two-step retrieval) kết hợp đa phương thức (Multimodal):

```
                  [Người dùng gửi câu hỏi]
                              │
                              ▼
                 [Chuẩn hóa câu hỏi thành]
                  [Standalone Question]
                              │
                              ▼
           ┌──────────────────┴──────────────────┐
           ▼                                     ▼
 [Tạo 3 câu trả lời giả định]          [Tìm kiếm tài liệu liên quan]
   (Hypothetical Answers)               (Embed Standalone Question)
           │                                     │
           │                                     ▼
           │                           [Pinecone: Match Vector Summary]
           │                            (Lọc ra top 10 storage_paths)
           │                                     │
           └──────────────────┬──────────────────┘
                              ▼
              [Truy vấn nội dung chi tiết]
             (Scoped theo 10 storage_paths)
                              │
         ┌────────────────────┴────────────────────┐
         ▼ (Đối với Text Documents)                ▼ (Đối với Image/Scanned Documents)
  [Tìm kiếm Vector Chunks]                  [Lấy trực tiếp file_url của PDF]
  - Dùng 3 Hypothetical Answers             (Không có text chunks để tìm kiếm)
  - Lấy top chunks khớp nhất
  - Lấy text thô tương ứng từ Supabase
         │                                         │
         └────────────────────┬────────────────────┘
                              ▼
                 [Xây dựng Multimodal Prompt]
                 - Text Context từ các chunks
                 - Các khối "image_url" trỏ trực tiếp
                   đến link PDF scan trên Cloud
                 - Standalone Question & Luật trích dẫn
                              │
                              ▼
                   [Gọi Gemini 3.5 Flash]
                   (Đọc cả text context & trực tiếp
                    phân tích nội dung file PDF scan)
                              │
                              ▼
               [Trả về Câu trả lời + Citations]
```

##### Chi tiết các bước xử lý (`rag_service.py`):
1. **Chuẩn hóa & Mở rộng câu hỏi**:
   - Lịch sử chat và tin nhắn mới nhất được gửi qua LLM để viết lại thành một câu hỏi độc lập duy nhất (**Standalone Question**), loại bỏ các từ ngữ mơ hồ hoặc tham chiếu cũ.
   - Viết lại Standalone Question thành 3 câu trả lời giả định (**Hypothetical Answers**) khác nhau nhằm tăng diện tích tiếp xúc ngữ nghĩa khi tìm kiếm chi tiết.
2. **Bước 1: Định tuyến Tài liệu (Document Filtering)**:
   - Chuyển đổi Standalone Question thành vector và truy vấn trong Pinecone, chỉ tìm các vector có `isDocument: True`.
   - Kết quả trả về danh sách top 10 đường dẫn tài liệu (`storage_path`) có khả năng chứa câu trả lời cao nhất.
3. **Bước 2: Tìm kiếm ngữ cảnh chi tiết (Scoped Retrieval)**:
   - Bộ lọc được cấu hình để giới hạn phạm vi tìm kiếm chỉ nằm trong 10 tài liệu đã tìm thấy ở Bước 1.
   - **Đối với tài liệu văn bản thông thường**: Hệ thống dùng 3 Hypothetical Answers để tìm kiếm các vector chunk có độ tương quan cao nhất trên Pinecone, sau đó lấy nội dung text thô tương ứng từ bảng `document_chunks` của Supabase làm `text_context`.
   - **Đối với tài liệu quét (scanned PDF)**: Hệ thống lấy thông tin tham chiếu và `file_url` trực tiếp của tài liệu từ Supabase.
4. **Xây dựng Prompt đa phương thức (Multimodal Assembly)**:
   - Hệ thống đính kèm phần ngữ cảnh văn bản thô vào Prompt.
   - Đối với tài liệu scan/hình ảnh, hệ thống chèn trực tiếp các khối nội dung dạng `"image_url"` chứa URL của file PDF gốc để LLM tự đọc (Gemini có khả năng phân tích trực tiếp file PDF không cần chuyển đổi sang ảnh).
   - Áp dụng các luật trích dẫn nguồn nghiêm ngặt (đối với văn bản: định dạng `[source - Trang page](chunk_id)`; đối với tài liệu quét: định dạng `[tên tài liệu - scan PDF](doc-document_id)`).
5. **Sinh câu trả lời**:
   - Gửi prompt đa phương thức đến **Google Gemini LLM** (`gemini-3.1-flash-lite` hoặc các dòng Gemini mới hỗ trợ xử lý file PDF trực tiếp) để tổng hợp câu trả lời tự nhiên, chính xác nhất và trả về cho người dùng kèm các link trích dẫn nguồn gốc.

---

## 🛠️ Công Nghệ Sử Dụng (Tech Stack)

| Thành phần | Công nghệ / Thư viện | Mô tả |
| :--- | :--- | :--- |
| **Frontend** | Next.js 15, React, TypeScript, Tailwind CSS | Giao diện trò chuyện mượt mà, quản lý cấu trúc thư mục, hiển thị tài liệu trực quan. |
| **Backend** | FastAPI, Python 3.10, Uvicorn | API hiệu năng cao, xử lý song song và tích hợp bất đồng bộ. |
| **Orchestration** | LangChain | Quản lý chuỗi xử lý RAG, kết nối LLM và Vector Store. |
| **LLM & Embeddings** | Google Gemini API (`gemini-embedding-2`, Generative Models) | Tạo vector nhúng chất lượng cao và sinh câu trả lời tự nhiên. |
| **Cơ sở dữ liệu** | Supabase (PostgreSQL) | Lưu trữ thông tin người dùng, lịch sử chat, cấu trúc thư mục, metadata tài liệu. |
| **Lưu trữ file** | Supabase Storage | Lưu trữ file PDF và hình ảnh gốc do người dùng upload. |
| **Vector Database** | Pinecone DB | Tìm kiếm tương đồng vector với tốc độ mili-giây. |
| **Đóng gói** | Docker & Docker Compose | Đóng gói ứng dụng thành container độc lập giúp dễ dàng chạy local và deploy. |

---

## 📁 Cấu Trúc Thư Mục Dự Án

```
Menas_HR_bot/
├── backend/                  # Mã nguồn FastAPI Backend
│   ├── src/
│   │   ├── api/              # Định nghĩa API Routes (`routes.py`)
│   │   ├── db/               # Kết nối Supabase database client
│   │   ├── services/         # Logic cốt lõi (RAG, Chat, PDF processing, Folders, v.v.)
│   │   └── utils/            # Các hàm tiện ích (Logging, helpers...)
│   ├── Dockerfile            # Dockerfile độc lập cho backend
│   └── requirements.txt      # Thư viện Python cần thiết
├── frontend/                 # Mã nguồn Next.js Frontend
│   ├── src/
│   │   ├── app/              # Next.js App Router (trang chat, routing)
│   │   ├── components/       # Các UI Component chính (`ChatUI.tsx` chiếm chủ đạo)
│   │   └── lib/              # Các hàm kết nối API, Supabase client
│   ├── Dockerfile            # Dockerfile độc lập cho frontend
│   └── package.json          # Quản lý thư viện frontend
├── database/                 # Chứa script khởi tạo database
│   └── init.sql              # Script SQL thiết lập bảng & trigger trên Supabase
├── Dockerfile                # Dockerfile gộp (Multi-stage) dùng cho deploy Render
├── docker-compose.yml        # Docker Compose chạy toàn bộ hệ thống ở Local
├── start.sh                  # Script khởi động gộp cả Backend và Frontend trong 1 container
└── render.yaml               # Cấu hình deployment tự động lên Render
```

---

## ⚙️ Cấu Hình Biến Môi Trường (Environment Variables)

### 1. Cấu hình Backend (`backend/.env`)
Tạo file `backend/.env` từ file mẫu và điền các giá trị:
```env
# Google Gemini API
GEMINI_API_KEY="AIzaSyChpUS..."

# Pinecone Vector Database
PINECONE_API_KEY="pcsk_3zyK..."
PINECONE_INDEX_NAME="test-index"

# Supabase (Database & Storage)
SUPABASE_URL="https://wlxvinw..."
SUPABASE_PUBLISHABLE_KEY="sb_publishable_..."
SUPABASE_SECRET_ROLE_KEY="sb_secret_..."

# Cơ sở dữ liệu quan hệ (PostgreSQL)
DATABASE_URL="postgresql://admin:123456@localhost:5432/menas_hr_db"
```

### 2. Cấu hình Frontend (`frontend/.env.local`)
Tạo file `frontend/.env.local` với các nội dung sau:
```env
NEXT_PUBLIC_SUPABASE_URL="https://wlxvinw..."
NEXT_PUBLIC_SUPABASE_ANON_KEY="eyJhbGciOiJIUz..."

# URL của Backend API (dùng để Next.js proxy request sang Backend)
# Chạy local không docker: http://127.0.0.1:8000
# Chạy bằng docker-compose: http://backend:8000
NEXT_PUBLIC_BACKEND_URL="http://127.0.0.1:8000"
```

---

## 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy Local

Chọn một trong các cách dưới đây để chạy hệ thống ở máy cá nhân:

### Cách 1: Chạy bằng Docker Compose (Khuyên dùng)
Yêu cầu đã cài đặt **Docker** và **Docker Desktop**.
1. Đảm bảo file `frontend/.env.local` có cấu hình `NEXT_PUBLIC_BACKEND_URL=http://backend:8000`.
2. Tại thư mục gốc của dự án, chạy lệnh:
   ```bash
   docker-compose up --build
   ```
3. Sau khi khởi động thành công:
   - Frontend sẽ chạy tại: [http://localhost:3000](http://localhost:3000)
   - Backend API chạy tại: [http://localhost:8000](http://localhost:8000)

---

### Cách 2: Khởi chạy thủ công (Manual Setup)
Yêu cầu cài đặt **Python 3.10+** và **Node.js 20+**.

#### Khởi chạy Backend:
1. Di chuyển vào thư mục backend:
   ```bash
   cd backend
   ```
2. Tạo môi trường ảo và cài đặt thư viện:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Trên Windows dùng: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Chạy backend server:
   ```bash
   uvicorn src.api.routes:app --host 127.0.0.1 --port 8000 --reload
   ```

#### Khởi chạy Frontend:
1. Mở một terminal mới và di chuyển vào thư mục frontend:
   ```bash
   cd frontend
   ```
2. Đảm bảo cấu hình `NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000` trong file `frontend/.env.local`.
3. Cài đặt thư viện và chạy môi trường dev:
   ```bash
   npm install
   npm run dev
   ```
4. Truy cập giao diện tại: [http://localhost:3000](http://localhost:3000).


---

## 🔒 Bản Quyền & Bảo Trì
Dự án được phát triển cho mục đích quản trị nhân sự nội bộ. Mọi thắc mắc và hỗ trợ kỹ thuật, vui lòng liên hệ bộ phận phát triển hệ thống.
