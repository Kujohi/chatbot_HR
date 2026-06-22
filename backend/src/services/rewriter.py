from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel, Field

from src.services.gemini_config import GEMINI_UTILITY_MODEL
from src.services.llm import chat_complete, chat_complete_with_structured

logger = logging.getLogger(__name__)


class HypoAnswers(BaseModel):
    hypo_answers: List[str] = Field(description="List of hypothesis answers")


def summarized_question(history, question: str) -> str:
    """
    Rewrite a question to a standalone question
    """
    system_prompt = """
Bạn là trợ lý AI chuyên viết lại câu hỏi liên quan đến quy định của công ty.

Nhiệm vụ của bạn là chuyển câu hỏi hoặc tin nhắn hiện tại của người dùng thành một phiên bản có thể hiểu độc lập mà không cần đọc lịch sử hội thoại.

Quy tắc:

1. Giữ nguyên ý nghĩa, mục đích và ngữ cảnh của câu hỏi gốc.
2. Thay thế mọi đại từ hoặc cách gọi mơ hồ (ví dụ: nó, cái đó, việc đó, trường hợp này, như trên...) bằng nội dung cụ thể tương ứng.
3. Chỉ viết lại khi cần thiết để câu hỏi có thể hiểu độc lập. Nếu câu hỏi đã rõ ràng, trả về nguyên văn.
4. Không trả lời câu hỏi, không bổ sung thông tin, không giải thích.
5. Chỉ xuất ra duy nhất nội dung câu hỏi đã được viết lại hoặc nội dung gốc nếu không cần viết lại.
6. Nếu người dùng gửi lời chào, cảm ơn, hoặc bất kỳ nội dung nào không phải câu hỏi, hãy trả về nguyên văn nội dung đó.
7. Tuyệt đối không chào hỏi, không giới thiệu bản thân, không đóng vai trợ lý hỗ trợ khách hàng, không tạo hội thoại mới.
8. Đầu ra chỉ gồm một câu duy nhất là kết quả viết lại, không có tiền tố, hậu tố hoặc giải thích.
"""

    user_prompt = f"""
    Lịch sử hội thoại:
    {history}

    Câu hỏi hiện tại cần viết lại:
    {question}
    """
    return chat_complete(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model_name=GEMINI_UTILITY_MODEL,
    )


def rewrite_query_hypo_answers(standalone_question: str, num_hypo_answers: int = 3) -> List[str]:
    """
    Rewrite a question to multiple hypothesis answers
    """
    system_prompt = f"""
    Bạn là trợ lý AI chuyên về hỏi đáp quy định công ty. 
    1. Nhiệm vụ của bạn là viết lại câu hỏi thành {num_hypo_answers} câu trả lời giả định khác nhau để thuận tiện trong việc truy vấn.
    2. Ưu tiên nếu câu hỏi gồm nhiều ý hãy phân tách thành các trả lời con cho từng ý.
    3. Nếu câu hỏi chỉ có một ý thì viết lại thành nhiều biến thể trả lời giả định.
    Output format:
    
    """
    user_prompt = f"""
    Câu hỏi hiện tại:
    {standalone_question}
    """
    result = chat_complete_with_structured(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        HypoAnswers,
        model_name=GEMINI_UTILITY_MODEL,
    )
    return result.hypo_answers


def rewrite_path_to_summary(path: str) -> str:
    """
    Rewrite a path to a summary
    """
    system_prompt = f"""
    Bạn là trợ lý của hệ thống AI chuyên về hỏi đáp quy định công ty Menas.
    Dựa trên đường dẫn được cung cấp, viết một đoạn summary dự đoán cho tài liệu này để thuận tiện cho việc truy vấn dữ liệu.
    Không cần lời giới thiệu, không cần giải thích. Chỉ đơn giản đưa ra đoạn summary.
    Output format:
    - Tên tài liệu:
    - Đoạn summary:
    - Từ khóa tìm kiếm:
    """
    user_prompt = f"""
    Đường dẫn tài liệu:
    {path}
    """
    return chat_complete(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model_name=GEMINI_UTILITY_MODEL,
    )
