import logging
from typing import List

from pydantic import BaseModel, Field

from src.services.llm import chat_complete_with_structured
from src.services.retrieval_service import search_document_summaries
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

class DocumentPaths(BaseModel):
    document_paths: List[str] = Field(description="List of document paths, each path is a string")

def format_document_path(document_paths: List[str]) -> str:
    formatted_document_paths = ""
    for document_path in document_paths:
        formatted_document_paths += f"{document_path}\n"
    return formatted_document_paths

def filter_documents(standalone_question: str, limit: int = 5) -> List[str]:
    """
    Filter the documents that are relevant to the question
    """
    document_paths = search_document_summaries(standalone_question.strip(), limit=limit)
    formatted_document_paths = format_document_path(document_paths)
    system_prompt = """
    Bạn là trợ lý AI chuyên về hỏi đáp quy định công ty Menas.
    Dựa trên các tài liệu được cung cấp, hãy lọc ra các đường dẫn tài liệu mà người dùng có thể quan tâm.
    """
    user_prompt = f"""
    Câu hỏi: {standalone_question}
    Các đường dẫn tài liệu được cung cấp: \n{formatted_document_paths}
    """
    result = chat_complete_with_structured([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], DocumentPaths)
    
    mapped_paths = []
    for llm_path in result.document_paths:
        best_match = None
        best_score = 0
        for orig_path in document_paths:
            score = fuzz.ratio(llm_path, orig_path)
            if score > best_score:
                best_score = score
                best_match = orig_path
        if best_score >= 90 and best_match:
            mapped_paths.append(best_match)
        else:
            logger.warning(f"Could not map LLM path '{llm_path}' to original path. Best match was '{best_match}' with score {best_score}%")
            
    return mapped_paths

if __name__ == "__main__":
    print(filter_documents("Quy định đồng phục cho nhân viên Skyshop tại công ty Menas là gì?"))