# 📖 Hướng Dẫn Sử Dụng Menas HR Bot

Tài liệu này hướng dẫn chi tiết cách sử dụng các tính năng trên giao diện của **Menas HR Bot** dành cho Quản trị viên nhân sự và Nhân viên.

---

## 📋 Mục Lục
1. [Giới thiệu Giao diện Tổng quan](#1-giới-thiệu-giao-diện-tổng-quan)
2. [Quản lý Thư mục Tài liệu (Folders)](#2-quản-lý-thư-mục-tài-liệu-folders)
3. [Tải lên và Quản lý Tài liệu Nhân sự (Documents)](#3-tải-lên-và-quản-lý-tài-liệu-nhân-sự-documents)
4. [Trò chuyện & Hỏi đáp với HR Bot (RAG Chat)](#4-trò-chuyện--hỏi-đáp-với-hr-bot-rag-chat)
5. [Quản lý Lịch sử Hội thoại (Threads)](#5-quản-lý-lịch-sử-hội-thoại-threads)

---

## 1. Giới thiệu Giao diện Tổng quan

Khi truy cập vào đường dẫn ứng dụng Menas HR Bot, bạn sẽ thấy giao diện được chia làm 3 phần chính:
1. **Thanh bên trái (Sidebar)**: Chứa danh sách các cuộc hội thoại cũ (Lịch sử chat) và nút tạo phiên chat mới.
2. **Khu vực trung tâm (Chat Area)**: Không gian trò chuyện chính với Trợ lý ảo.
3. **Thanh bên phải (Knowledge Base Pane)**: Nơi quản lý cấu trúc thư mục tài liệu, tải file lên hệ thống và hiển thị danh sách tài liệu hiện có.

```
[Chèn hình ảnh: Giao diện tổng quan của ứng dụng Menas HR Bot]
Mô tả ảnh: Ảnh chụp màn hình toàn bộ trình duyệt, thể hiện Sidebar lịch sử chat bên trái, khung chat ở giữa và bảng quản lý tài liệu Knowledge Base bên phải.
```

---

## 2. Quản lý Thư mục Tài liệu (Folders)

Tài liệu nhân sự cần được phân chia theo các phòng ban hoặc chủ đề (ví dụ: Quy chế công ty, Phúc lợi, Bảo hiểm, Quy trình đào tạo) để dễ quản lý.

### 2.1 Xem cấu trúc thư mục
- Ở cột **Knowledge Base** phía bên phải, bạn sẽ thấy danh sách các thư mục hiện có.
- Thư mục mặc định là **General**.
- Bạn có thể nhấp chuột vào một thư mục để đi vào bên trong. Thanh điều hướng thư mục (Breadcrumb) phía trên sẽ hiển thị đường dẫn hiện tại giúp bạn quay lại thư mục cha một cách dễ dàng.

```
[Chèn hình ảnh: Thanh điều hướng Breadcrumb và Danh sách thư mục]
Mô tả ảnh: Ảnh chụp phần đầu cột Knowledge Base, làm nổi bật đường dẫn Breadcrumb (ví dụ: General > Quy chế lao động) và danh sách các thư mục con bên dưới.
```

### 2.2 Tạo thư mục mới
1. Đi tới thư mục cha mà bạn muốn tạo thư mục con bên trong (hoặc ở ngay thư mục gốc).
2. Nhấn nút **Create Folder** (hoặc biểu tượng thư mục mới).
3. Nhập **Tên thư mục** (Folder Name) và **Mô tả** (Description) nếu cần.
4. Nhấn **Confirm** để tạo. Thư mục mới xuất hiện ngay lập tức trong danh sách.

```
[Chèn hình ảnh: Form tạo thư mục mới]
Mô tả ảnh: Ảnh chụp hộp thoại Popup hiện lên khi người dùng nhấn "Create Folder", hiển thị các trường nhập thông tin như Name và Description.
```

### 2.3 Xóa thư mục
- Di chuột qua thư mục cần xóa, nhấn vào biểu tượng **Thùng rác** (Delete) bên cạnh tên thư mục.
- Hệ thống sẽ hiển thị cảnh báo xác nhận xóa.
- **Lưu ý**: Khi xóa thư mục, tất cả các thư mục con và tài liệu bên trong cũng sẽ bị xóa khỏi cơ sở dữ liệu và Pinecone Vector Store.

---

## 3. Tải lên và Quản lý Tài liệu Nhân sự (Documents)

Để HR Bot có thể trả lời các câu hỏi, bạn cần cung cấp "kiến thức" cho nó bằng cách tải lên các tài liệu chính sách của công ty.

### 3.1 Tải lên tài liệu mới (PDF hoặc Hình ảnh)
1. Chọn thư mục lưu trữ phù hợp ở bảng bên phải.
2. Kéo thả file tài liệu vào khu vực tải lên hoặc click chọn nút **Upload Document**.
   - Định dạng hỗ trợ tốt nhất: **PDF** (cả file văn bản và file scan) hoặc các định dạng hình ảnh chính sách (**PNG, JPG**).
3. Nhập tiêu đề tài liệu (nếu muốn thay đổi so với tên file).
4. Nhấn **Upload** để bắt đầu quá trình xử lý.
5. **Quá trình RAG xử lý tự động phía sau**:
   - Backend sẽ tự động lưu file lên Supabase Storage.
   - Trích xuất toàn bộ văn bản và cắt nhỏ thành các đoạn (chunks).
   - Tiến hành hóa vector qua Google Gemini Embedding và lưu vào Pinecone Vector DB.
   - Khi trạng thái chuyển sang **Success / Complete**, tài liệu đã sẵn sàng để được Bot sử dụng.

```
[Chèn hình ảnh: Giao diện tải file tài liệu]
Mô tả ảnh: Ảnh chụp vùng Upload file, cho thấy người dùng kéo thả file PDF vào và nhấn nút Upload, kèm thanh tiến trình xử lý.
```

### 3.2 Xóa tài liệu
- Để gỡ bỏ một tài liệu cũ hoặc hết hiệu lực: Nhấp vào biểu tượng **Xóa** (thùng rác) bên cạnh tên tài liệu trong danh sách.
- Hệ thống sẽ tự động xóa file trên Supabase Storage, xóa dữ liệu liên quan trong Supabase PostgreSQL và đồng thời xóa các vector nhúng tương ứng trên Pinecone DB để tránh việc Bot tiếp tục tham chiếu đến thông tin cũ.

---

## 4. Trò chuyện & Hỏi đáp với HR Bot (RAG Chat)

Tính năng cốt lõi dành cho tất cả nhân viên để tra cứu thông tin nhanh chóng.

### 4.1 Bắt đầu cuộc trò chuyện mới
- Tại sidebar bên trái, nhấn vào nút **New Chat** (hoặc biểu tượng dấu cộng `+`).
- Một phiên chat mới sạch sẽ sẽ được tạo ra ở khung giữa.

### 4.2 Gửi câu hỏi và Nhận câu trả lời
- Nhập câu hỏi cần giải đáp vào khung chat phía dưới (ví dụ: *"Chính sách nghỉ phép năm của công ty quy định thế nào?"* hoặc *"Thứ 2 có bắt buộc mặc đồng phục không?"*).
- Nhấn **Enter** hoặc click biểu tượng gửi tin nhắn.
- Trợ lý ảo sẽ hiển thị trạng thái đang xử lý và phản hồi lại câu trả lời sau vài giây.

```
[Chèn hình ảnh: Hộp thoại trò chuyện đang hoạt động]
Mô tả ảnh: Khung chat trung tâm hiển thị câu hỏi của nhân viên và câu trả lời hoàn chỉnh được trả về từ HR Bot.
```

### 4.3 Xem trích dẫn nguồn tài liệu tham chiếu (Citations)
- Để đảm bảo tính minh bạch và độ chính xác, dưới mỗi câu trả lời của Bot thường đi kèm phần **Nguồn tham chiếu** (Citations / Sources).
- Bạn có thể click vào các nguồn này để xem chi tiết đoạn văn bản thô nào trong tài liệu đã được Bot sử dụng để tạo ra câu trả lời đó. Điều này giúp nhân viên tự xác minh độ tin cậy của thông tin mà không sợ hiện tượng LLM tự bịa thông tin (hallucination).

```
[Chèn hình ảnh: Chi tiết nguồn trích dẫn tài liệu]
Mô tả ảnh: Ảnh chụp khu vực hiển thị các nguồn tham chiếu (ví dụ: [1] Quy_dinh_nhan_su.pdf - trang 3) phía dưới câu trả lời của Bot, hiển thị nội dung trích xuất khi click vào.
```

---

## 5. Quản lý Lịch sử Hội thoại (Threads)

Hệ thống tự động lưu trữ các cuộc hội thoại cũ để bạn có thể xem lại bất cứ lúc nào.

- **Xem lại chat cũ**: Danh sách các phiên trò chuyện (Threads) hiển thị ở Sidebar bên trái theo thời gian tạo. Click chọn một thread bất kỳ để tải lại lịch sử tin nhắn của phiên đó.
- **Đổi tên / Quản lý thread**: Tên thread được tự sinh hoặc cập nhật tự động dựa trên nội dung câu hỏi đầu tiên của bạn.
- **Xóa cuộc trò chuyện**: Để xóa một phiên trò chuyện cũ, di chuột vào tên thread trong danh sách sidebar bên trái và click vào biểu tượng **Xóa** (thùng rác). Lịch sử tin nhắn của phiên này sẽ được dọn dẹp sạch sẽ khỏi hệ thống Supabase.

```
[Chèn hình ảnh: Danh sách lịch sử chat ở Sidebar trái]
Mô tả ảnh: Hình ảnh hiển thị cận cảnh sidebar bên trái với danh sách các tiêu đề cuộc trò chuyện khác nhau và nút xóa xuất hiện khi di chuột qua.
```

---

## 💡 Mẹo Để Hỏi Bot Hiệu Quả Nhất
1. **Đặt câu hỏi rõ ràng**: Hãy đặt câu hỏi chứa từ khóa cụ thể có trong tài liệu của bạn (ví dụ: Thay vì hỏi *"nghỉ thế nào?"*, hãy hỏi *"Quy trình xin nghỉ phép năm cần gửi trước mấy ngày?"*).
2. **Cập nhật tài liệu mới nhất**: Hãy chắc chắn các quy định mới nhất đã được tải lên và các tài liệu cũ đã được xóa bỏ để Bot không lấy nhầm dữ liệu đã hết hạn.
3. **Kiểm tra nguồn trích dẫn**: Luôn tận dụng tính năng nhấn vào nguồn tham chiếu để đối chiếu trực tiếp với quy chế chuẩn của công ty khi thực hiện các thủ tục nhân sự quan trọng.
