import logging
from typing import List, Dict

from src.services.retrieval_service import search_documents
from src.services.llm import chat_complete
from src.services.rewriter import rewrite_query_hypo_answers
from src.services.document_filter import filter_documents

logger = logging.getLogger(__name__)

TEXT_CITATION_RULE = (
    "5. QUAN TRỌNG: Khi trích dẫn thông tin từ tài liệu, BẮT BUỘC phải định dạng trích dẫn "
    "theo cú pháp [source - Trang page_number](chunk_id), trong đó thay thế source, page_number "
    "và chunk_id là các giá trị tương ứng được cung cấp trong phần metadata của mỗi tài liệu."
)
IMAGE_CITATION_RULE = (
    "5. QUAN TRỌNG: Với tài liệu quét (hình ảnh), trích dẫn theo cú pháp "
    "[tên tài liệu - scan PDF](doc-document_id), ví dụ [Chính sách - scan PDF](doc-39). "
    "Không dùng số trang hay chunk_id cho tài liệu quét."
)


def _build_rag_user_content(
    text_context: str,
    image_documents: List[Dict],
    standalone_question: str,
) -> List[Dict]:
    content_blocks: List[Dict] = []

    if text_context.strip():
        content_blocks.append(
            {
                "type": "text",
                "text": (
                    "Tài liệu văn bản được trích xuất (có chunk_id và số trang):\n"
                    f"{text_context}"
                ),
            }
        )

    for image_doc in image_documents:
        content_blocks.append(
            {
                "type": "text",
                "text": (
                    f"Tài liệu quét (toàn bộ PDF dưới dạng hình ảnh): "
                    f"{image_doc['title']} (citation link id: doc-{image_doc.get('document_id')}, "
                    f"path: {image_doc['storage_path']})"
                ),
            }
        )
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": image_doc["file_url"],
            }
        )

    content_blocks.append(
        {
            "type": "text",
            "text": (
                f"\n\nCâu hỏi: {standalone_question}\n\n"
                "Hãy trả lời dựa trên các tài liệu quy định công ty Menas trên."
            ),
        }
    )
    return content_blocks


def bot_rag_answer_message(standalone_question):
    """
    Enhanced RAG pipeline with:
    2. Multi hypothesis answer retrieval
    3. Text chunks for normal PDFs; full-page images for scanned PDFs
    4. Improved prompting for Vietnamese legal context
    """
    document_paths = filter_documents(standalone_question, 10)
    hypo_answers = rewrite_query_hypo_answers(standalone_question)
    retrieved = search_documents(document_paths, hypo_answers, limit=3)
    text_context = retrieved.get("text_context", "")
    image_documents = retrieved.get("image_documents", [])

    citation_rule = IMAGE_CITATION_RULE if image_documents else TEXT_CITATION_RULE
    if text_context and image_documents:
        citation_rule = f"{TEXT_CITATION_RULE}\n{IMAGE_CITATION_RULE}"

    system_prompt = f"""Bạn là trợ lý AI chuyên về hỏi đáp quy định công ty Menas. Nhiệm vụ của bạn là:
1. Trả lời câu hỏi dựa trên các tài liệu quy định công ty Menas nếu có liên quan.
2. Trích dẫn chính xác các điều khoản, khoản, điểm từ văn bản quy định công ty Menas nếu có
3. Không phải tài liệu nào được trích xuất cũng liên quan (không cần nhắc tới khi trả lời), nếu không trả lời được thì chỉ cần trả lời không có thông tin rõ ràng.
4. BẮT BUỘC trả lời trực tiếp câu hỏi, không lan man về các vấn đề khác.
{citation_rule}"""

    structured_messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": _build_rag_user_content(
                text_context, image_documents, standalone_question
            ),
        },
    ]

    logger.info(
        "Sending RAG request (%s text context, %s image documents)",
        bool(text_context.strip()),
        len(image_documents),
    )

    assistant_answer = chat_complete(structured_messages)

    logger.info("Bot RAG reply generated successfully")
    return assistant_answer

if __name__ == "__main__":
    print(bot_rag_answer_message("điều kiện dành cho nhân viên nấu bún chả là gì?"))