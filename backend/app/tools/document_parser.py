"""
Document parser tool for PDF text extraction
"""

import fitz  # PyMuPDF
import pdfplumber
from typing import Optional
from pathlib import Path
import logging

logger = logging.getLogger("fundflow")


class PDFParser:
    """PDF parser with PyMuPDF primary and pdfplumber fallback"""
    
    @staticmethod
    def extract_text_pymupdf(file_path: str) -> Optional[str]:
        """
        Extract text from PDF using PyMuPDF (fitz)
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text or None if failed
        """
        try:
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text.strip() if text.strip() else None
        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {e}")
            return None
    
    @staticmethod
    def extract_text_pdfplumber(file_path: str) -> Optional[str]:
        """
        Extract text from PDF using pdfplumber (fallback)
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text or None if failed
        """
        try:
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            return text.strip() if text.strip() else None
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            return None
    
    @staticmethod
    def extract_text(file_path: str) -> str:
        """
        Extract text from PDF with automatic fallback
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text
            
        Raises:
            ValueError: If both extraction methods fail
        """
        # Validate file exists
        if not Path(file_path).exists():
            raise ValueError(f"File not found: {file_path}")
        
        # Try PyMuPDF first
        text = PDFParser.extract_text_pymupdf(file_path)
        if text:
            logger.info("Successfully extracted text using PyMuPDF")
            return text
        
        # Fallback to pdfplumber
        text = PDFParser.extract_text_pdfplumber(file_path)
        if text:
            logger.info("Successfully extracted text using pdfplumber fallback")
            return text
        
        raise ValueError("Failed to extract text from PDF using both methods")
    
    @staticmethod
    def validate_pdf(file_path: str) -> bool:
        """
        Validate if file is a valid PDF
        
        Args:
            file_path: Path to file
            
        Returns:
            True if valid PDF, False otherwise
        """
        try:
            doc = fitz.open(file_path)
            doc.close()
            return True
        except Exception:
            return False
