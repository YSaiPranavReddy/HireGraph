import fitz  # PyMuPDF
import os
from typing import List


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract raw text from a single PDF file."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception as e:
        return f"ERROR reading {pdf_path}: {str(e)}"


def load_resumes_from_folder(folder_path: str) -> List[dict]:
    """
    Load all PDFs from a folder.
    Returns: [{"file_name": "john_doe.pdf", "raw_text": "..."}]
    """
    resumes = []
    if not os.path.exists(folder_path):
        return resumes

    for file in os.listdir(folder_path):
        if file.endswith(".pdf"):
            full_path = os.path.join(folder_path, file)
            raw_text = extract_text_from_pdf(full_path)
            resumes.append({
                "file_name": file,
                "raw_text": raw_text
            })

    return resumes


def load_jd_from_text(jd_text: str) -> str:
    """Pass-through for JD text input (from UI text area)."""
    return jd_text.strip()


def load_jd_from_pdf(pdf_path: str) -> str:
    """Extract JD text if uploaded as PDF."""
    return extract_text_from_pdf(pdf_path)