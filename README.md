# 🤖 Menas HR Bot - Trợ Lý Ảo Nhân Sự Thông Minh (RAG-based)

Dự án **Menas HR Bot** là một hệ thống Trợ lý ảo Nhân sự được xây dựng trên công nghệ **RAG (Retrieval-Augmented Generation)**. Hệ thống giúp tự động hóa việc giải đáp các thắc mắc của nhân viên liên quan đến quy định, chính sách, thủ tục nhân sự của công ty bằng cách truy vấn thông tin trực tiếp từ cơ sở dữ liệu tri thức (tài liệu PDF, hình ảnh chính sách...) được tải lên bởi quản trị viên.

---

## 📌 Phân Mục Tài Liệu
* 📖 [Hướng dẫn Sử dụng chi tiết (User Guide)](file:///Users/doduyhiep/HR_AI/Menas_HR_bot/USER_GUIDE.md) - Tài liệu dành cho quản trị viên và người dùng cuối.

---

## 🏛️ Kiến Trúc Hệ Thống (System Architecture)

Hệ thống hoạt động theo mô hình **Client-Server** kết hợp cơ chế **RAG** để cung cấp câu trả lời có tính xác thực cao dựa trên tài liệu nội bộ.

### 🖼️ Sơ Đồ Kiến Trúc Tổng Quan
```
[Chèn sơ đồ kiến trúc hệ thống tổng quan ở đây]
Ví dụ: Sơ đồ tương tác giữa Frontend (Next.js) <-> Backend (FastAPI) <-> PostgreSQL + pgvector & LLM (Gemini API) & SharePoint
```
*(Vui lòng thiết kế hình ảnh sơ đồ kiến trúc và thay thế vào vị trí placeholder trên)*

---

### 🔄 Luồng Hoạt Động (Data Flow)

#### 1. Luồng Tải lên & Xử lý Tài liệu (Indexing Pipeline)
```
[File PDF/Ảnh] ──> [Tải lên Frontend] ──> [FastAPI Backend]
                                                 │
      ┌──────────────────────────────────────────┴──────────────────────────────────────────┐
      ▼ (Lưu trữ file gốc)                                                                  ▼ (Xử lý văn bản)
[SharePoint]                                                                      [Đọc & Trích xuất chữ]
                                                                                            │
                                                                                            ▼
                                                                                   [Cắt nhỏ thành Chunks]
                                                                                            │
                                                                       ┌────────────────────┴────────────────────┐
                                                                       ▼ (Tạo Vector)                            ▼ (Lưu Metadata)
                                                               [Gemini Embedding]                       [Supabase PostgreSQL]
                                                                 (embedding-2)                        (Thư mục, Tài liệu, Chunks)
                                                                       │
                                                                       ▼
[PostgreSQL + pgvector]
```
1. **Upload**: Quản trị viên tải tài liệu (dạng PDF hoặc hình ảnh) lên một thư mục cụ thể thông qua giao diện Frontend.
2. **Lưu trữ**: File gốc vẫn nằm ở **SharePoint**. Đồng thời thông tin tài liệu được ghi nhận vào bảng `documents` trong **PostgreSQL nội bộ**.
3. **Trích xuất & Cắt nhỏ (Chunking)**: Backend FastAPI sử dụng các thư viện xử lý tài liệu (`PyMuPDF`/`pdf_image.py`) để trích xuất văn bản từ PDF/Hình ảnh. Văn bản sau đó được chia nhỏ thành các đoạn ngắn (chunks) có độ dài tối ưu kèm theo metadata.
4. **Nhúng Vector (Embedding)**: Mỗi chunk văn bản được gửi qua **Google Gemini API** (model `gemini-embedding-2`) để tạo ra vector đặc trưng 3072 chiều.
5. **Đồng bộ hóa Vector DB & Relational DB**:
   - Vector và Metadata của chunk được lưu vào bảng `document_chunks` của **PostgreSQL + pgvector**.
   - Văn bản thô của chunk và id liên kết được lưu cùng bảng để đối chiếu khi hiển thị nguồn tham chiếu.

---

#### 2. Luồng Trò chuyện & Truy vấn (Retrieval-Augmented Generation - RAG Pipeline)
```
[Người dùng gửi câu hỏi] ──> [Frontend] ──> [FastAPI Backend]
                                                   │
                                                   ▼
                                      [Hóa vector câu hỏi bằng Gemini]
                                                   │
                                                   ▼ (Tìm kiếm ngữ cảnh tương đồng)
[PostgreSQL + pgvector]
                                                   │
                                                   ▼ (Trả về các chunks tương quan nhất)
[Lấy Chunks thô tương ứng từ PostgreSQL]
                                                   │
                                                   ▼
                                  [Tổng hợp Prompt: Ngữ cảnh + Câu hỏi]
                                                   │
                                                   ▼
                                           [Google Gemini LLM]
                                                   │
                                                   ▼ (Trả về câu trả lời + Trích dẫn nguồn)
[Hiển thị câu trả lời trực quan] <── [Frontend] <──┘
```
1. **Gửi câu hỏi**: Người dùng gửi tin nhắn hỏi về chính sách nhân sự thông qua giao diện chat.
2. **Truy vấn Vector**: Backend FastAPI nhận câu hỏi, chuyển đổi câu hỏi thành vector bằng `gemini-embedding-2` và truy vấn trên **PostgreSQL + pgvector** để tìm ra các đoạn văn bản có độ tương đồng ngữ nghĩa cao nhất.
3. **Tổng hợp Ngữ cảnh (Context assembly)**: Hệ thống lấy nội dung văn bản thô của các đoạn tương ứng từ PostgreSQL và tạo thành một Prompt hoàn chỉnh:
   * *Ngữ cảnh: [Các đoạn tài liệu tìm thấy]*
   * *Câu hỏi của người dùng: [Nội dung câu hỏi]*
   * *Yêu cầu: Hãy trả lời câu hỏi dựa trên ngữ cảnh được cung cấp. Nếu không có thông tin, hãy báo không biết, không tự bịa ra thông tin.*
4. **Sinh câu trả lời**: Prompt được gửi tới **Google Gemini LLM** để tạo câu trả lời tự nhiên, chính xác.
5. **Phản hồi**: Câu trả lời kèm danh sách tài liệu tham chiếu (Citations) được trả về Frontend để hiển thị trực quan cho người dùng. Toàn bộ hội thoại được lưu vào bảng `chat_conversations` trên PostgreSQL nội bộ.

---

## 🛠️ Công Nghệ Sử Dụng (Tech Stack)

| Thành phần | Công nghệ / Thư viện | Mô tả |
| :--- | :--- | :--- |
| **Frontend** | Next.js 15, React, TypeScript, Tailwind CSS | Giao diện trò chuyện mượt mà, quản lý cấu trúc thư mục, hiển thị tài liệu trực quan. |
| **Backend** | FastAPI, Python 3.10, Uvicorn | API hiệu năng cao, xử lý song song và tích hợp bất đồng bộ. |
| **Orchestration** | LangChain | Quản lý chuỗi xử lý RAG, kết nối LLM và Vector Store. |
| **LLM & Embeddings** | Google Gemini API (`gemini-embedding-2`, Generative Models) | Tạo vector nhúng chất lượng cao và sinh câu trả lời tự nhiên. |
| **Cơ sở dữ liệu** | PostgreSQL nội bộ | Lưu trữ thông tin người dùng, lịch sử chat, cấu trúc thư mục, metadata tài liệu. |
| **Lưu trữ file** | SharePoint | Lưu trữ file PDF và hình ảnh gốc do người dùng upload. |
| **Vector Database** | PostgreSQL + pgvector | Tìm kiếm tương đồng vector trực tiếp trong cùng hệ thống dữ liệu. |
| **Đóng gói** | Docker & Docker Compose | Đóng gói ứng dụng thành container độc lập giúp dễ dàng chạy local và deploy. |

---

## 📁 Cấu Trúc Thư Mục Dự Án

```
Menas_HR_bot/
├── backend/                  # Mã nguồn FastAPI Backend
│   ├── src/
│   │   ├── api/              # Định nghĩa API Routes (`routes.py`)
│   │   ├── db/               # Kết nối PostgreSQL database client
│   │   ├── services/         # Logic cốt lõi (RAG, Chat, PDF processing, Folders, v.v.)
│   │   └── utils/            # Các hàm tiện ích (Logging, helpers...)
│   ├── Dockerfile            # Dockerfile độc lập cho backend
│   └── requirements.txt      # Thư viện Python cần thiết
├── frontend/                 # Mã nguồn Next.js Frontend
│   ├── src/
│   │   ├── app/              # Next.js App Router (trang chat, routing)
│   │   ├── components/       # Các UI Component chính (`ChatUI.tsx` chiếm chủ đạo)
│   │   └── lib/              # Các hàm kết nối API
│   ├── Dockerfile            # Dockerfile độc lập cho frontend
│   └── package.json          # Quản lý thư viện frontend
├── database/                 # Chứa script khởi tạo database
│   └── init.sql              # Script SQL thiết lập bảng cho PostgreSQL nội bộ
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
GEMINI_CHAT_MODEL="gemini-3.5-flash"
GEMINI_UTILITY_MODEL="gemini-2.5-flash-lite"
GEMINI_EMBEDDING_MODEL="gemini-embedding-2"

# PostgreSQL + pgvector

# Cơ sở dữ liệu quan hệ (PostgreSQL)
DATABASE_URL="postgresql://admin:123456@localhost:5432/menas_hr_db"
```

### 2. Cấu hình Frontend (`frontend/.env.local`)
Tạo file `frontend/.env.local` với các nội dung sau:
```env
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

### Cách 3: Chạy thử Docker Single Container (Giống môi trường Render)
Để kiểm tra xem container gộp có chạy đúng trước khi deploy:
1. Đảm bảo cấu hình `NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000` trong file `frontend/.env.local`.
2. Build Docker image từ thư mục gốc:
   ```bash
   docker build -t menas-hr-bot:latest .
   ```
3. Chạy Docker container:
   ```bash
   docker run -p 3000:3000 --env-file backend/.env -e PORT=3000 menas-hr-bot:latest
   ```
4. Truy cập giao diện tại [http://localhost:3000](http://localhost:3000).

---

## ☁️ Hướng Dẫn Deploy Lên Render (Production Deployment)

Dự án đã được thiết kế tối ưu hóa để deploy lên **Render** chỉ trong một Web Service duy nhất thông qua Dockerfile gộp ở thư mục gốc.

### Các bước thực hiện:
1. Đẩy mã nguồn dự án lên một kho chứa Git cá nhân (GitHub / GitLab).
2. Đăng nhập vào tài liệu quản trị [Render Dashboard](https://dashboard.render.com/).
3. Chọn **New +** -> **Blueprint** để deploy tự động thông qua file `render.yaml`.
   * Hoặc nếu cấu hình thủ công: Chọn **Web Service**, chọn Git repository của bạn.
   * **Runtime**: Chọn `Docker`.
   * **Dockerfile Path**: `Dockerfile` (nằm ở thư mục gốc).
4. Thêm các biến môi trường cấu hình tại mục **Environment** trên Render:
   * Tất cả các biến môi trường trong file `backend/.env` (Gemini, SharePoint, PostgreSQL).
   * Các biến môi trường frontend cần thiết:
     - `NEXT_PUBLIC_BACKEND_URL` = `http://127.0.0.1:8000` (FastAPI chạy nội bộ bên trong cùng container).
5. Nhấn **Deploy** và đợi Render build & start. Hệ thống sẽ tự nhận cổng dịch vụ thông qua biến `$PORT` được Render cấp phát và chuyển tiếp yêu cầu đến Next.js trên cổng đó.

---

## 🔒 Bản Quyền & Bảo Trì
Dự án được phát triển cho mục đích quản trị nhân sự nội bộ. Mọi thắc mắc và hỗ trợ kỹ thuật, vui lòng liên hệ bộ phận phát triển hệ thống.
