import os
import re
# from datetime import date
from typing import Callable, Dict, List, Tuple
import langchain.docstore.document as docstore
import langchain.text_splitter as splitter
from loguru import logger
from pypdf import PdfReader
# local imports
from ingest.ingest_utils import getattr_or_default


class PdfParser:
    """A parser for extracting and cleaning text from PDF documents."""

    def __init__(self, chunk_size: int, chunk_overlap: int, file_no: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.file_no = file_no

    def set_pdf_file_path(self, pdf_file_path: str):
        """Set the path to the PDF file."""
        if not os.path.isfile(pdf_file_path):
            raise FileNotFoundError(f"File not found: {pdf_file_path}")
        self.pdf_file_path = pdf_file_path

    def clean_text_to_docs(self) -> List[docstore.Document]:
        raw_pages, metadata = self.parse_pdf()

        cleaning_functions: List = [
            self.merge_hyphenated_words,
            self.fix_newlines,
            self.remove_multiple_newlines,
        ]

        '''
        if self.file_no > 0:
            metadata['file_no'] = self.file_no
        '''

        cleaned_text_pdf = self.clean_text(raw_pages, cleaning_functions)
        return self.text_to_docs(cleaned_text_pdf, metadata)

    def parse_pdf(self) -> Tuple[List[Tuple[int, str]], Dict[str, str]]:
        """Extract and return the pages and metadata from the PDF."""
        metadata = self.extract_metadata_from_pdf()
        pages = self.extract_pages_from_pdf()
        return pages, metadata

    def extract_metadata_from_pdf(self) -> Dict[str, str]:
        """Extract and return the metadata from the PDF."""
        logger.info("Extracting metadata")
        with open(self.pdf_file_path, "rb") as pdf_file:
            reader = PdfReader(pdf_file)
            metadata = reader.metadata
            logger.info(f"{getattr(metadata, 'title', 'no title')}")
            # default_date = date(1900, 1, 1)
            return {
                # TODO add metadata title + pdf filename
                "title": getattr_or_default(metadata, 'title', '').strip(),
                "author": getattr_or_default(metadata, 'author', '').strip(),
                # "creation_date": getattr_or_default(metadata,
                #                                     'creation_date',
                #                                     default_date).strftime('%Y-%m-%d'),
            }

    def extract_pages_from_pdf(self) -> List[Tuple[int, str]]:
        """Extract and return the text of each page from the PDF."""
        logger.info("Extracting pages")
        with open(self.pdf_file_path, "rb") as pdf:
            reader = PdfReader(pdf)
            # numpages = len(reader.pages)
            return [(i + 1, p.extract_text())
                    for i, p in enumerate(reader.pages) if p.extract_text().strip()]

    def clean_text(self,
                   pages: List[Tuple[int, str]],
                   cleaning_functions: List[Callable[[str], str]]
                   ) -> List[Tuple[int, str]]:
        """Apply the cleaning functions to the text of each page."""
        logger.info("Cleaning text of each page")
        cleaned_pages = []
        for page_num, text in pages:
            for cleaning_function in cleaning_functions:
                text = cleaning_function(text)
            cleaned_pages.append((page_num, text))
        return cleaned_pages

    def merge_hyphenated_words(self, text: str) -> str:
        """Merge words in the text that have been split with a hyphen."""
        return re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    def fix_newlines(self, text: str) -> str:
        """Replace single newline characters in the text with spaces."""
        return re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    def remove_multiple_newlines(self, text: str) -> str:
        """Reduce multiple newline characters in the text to a single newline."""
        return re.sub(r"\n{2,}", "\n", text)

    def text_to_docs(self, text: List[Tuple[int, str]],
                     metadata: Dict[str, str]) -> List[docstore.Document]:
        """Split the text into chunks and return them as Documents."""
        doc_chunks: List[docstore.Document] = []

        chunk_no = 0
        for page_num, page in text:
            logger.info(f"Splitting page {page_num}")
            text_splitter = splitter.RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""],
                chunk_overlap=self.chunk_overlap,
            )
            chunks = text_splitter.split_text(page)
            for i, chunk in enumerate(chunks):
                if self.file_no:
                    metadata_combined = {
                        "file_no": self.file_no,
                        "chunk_no": chunk_no,
                        "source": f"F{self.file_no}-{chunk_no}"
                    }
                else:
                    metadata_combined = {
                        "page_number": page_num,
                        "chunk": i,
                        "source": f"p{page_num}-{i}",
                        **metadata,
                    }
                doc = docstore.Document(
                    page_content=chunk,
                    metadata=metadata_combined
                )
                doc_chunks.append(doc)
                chunk_no += 1
        return doc_chunks
