"""
PDF Consolidation Module
========================
Converts all files in a client folder to PDFs and concatenates them into a single file.

Author: Senior Software Engineer
Date: 2026-06-07
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
import tempfile
import shutil

try:
    from PyPDF2 import PdfMerger, PdfReader
    PYPDF2_AVAILABLE = True
    PYPDF_VERSION = 2
except ImportError:
    try:
        # pypdf 3.x+ uses PdfWriter instead of PdfMerger
        from pypdf import PdfWriter, PdfReader
        PYPDF2_AVAILABLE = True
        PYPDF_VERSION = 3
    except ImportError:
        PYPDF2_AVAILABLE = False
        PYPDF_VERSION = None
        logging.warning("PyPDF2/pypdf not available - PDF operations will fail")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("Pillow not available - image conversion will fail")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logging.warning("pandas not available - CSV/Excel conversion will be limited")

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logging.warning("python-docx not available - DOCX conversion will fail")

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logging.warning("reportlab not available - text conversion will fail")


class PDFConsolidator:
    """
    Handles conversion of various file formats to PDF and concatenation.

    Supports:
    - Text files (.txt, .md)
    - CSV files (.csv)
    - Excel files (.xlsx, .xls)
    - Word documents (.docx)
    - Images (.jpg, .jpeg, .png, .gif, .bmp)
    - Existing PDFs (.pdf)
    """

    SUPPORTED_EXTENSIONS = {
        '.pdf', '.txt', '.md', '.csv', '.xlsx', '.xls',
        '.docx', '.jpg', '.jpeg', '.png', '.gif', '.bmp'
    }

    def __init__(self, client_id: str, client_folder: Path):
        """
        Initialize PDF consolidator for a client.

        Args:
            client_id: Client identifier (e.g., 'merck_test')
            client_folder: Path to client's source folder
        """
        self.client_id = client_id
        self.client_folder = Path(client_folder)
        self.temp_dir = None
        self.converted_pdfs = []

    def __enter__(self):
        """Context manager entry - create temp directory."""
        self.temp_dir = tempfile.mkdtemp(prefix=f"pdf_conv_{self.client_id}_")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup temp files."""
        if self.temp_dir and Path(self.temp_dir).exists():
            try:
                shutil.rmtree(self.temp_dir)
                logging.debug(f"[{self.client_id}] Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                logging.warning(f"[{self.client_id}] Failed to cleanup temp dir: {e}")

    def find_source_files(self) -> List[Path]:
        """
        Find all supported files in client folder (non-recursive).

        Returns:
            List of Path objects for supported files
        """
        if not self.client_folder.exists():
            logging.error(f"[{self.client_id}] Folder not found: {self.client_folder}")
            return []

        files = []
        for item in self.client_folder.iterdir():
            if item.is_file() and not item.name.startswith('.'):
                if item.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    files.append(item)
                else:
                    logging.debug(f"[{self.client_id}] Skipping unsupported: {item.name}")

        # Sort for consistent ordering
        files.sort(key=lambda x: x.name.lower())
        logging.info(f"[{self.client_id}] Found {len(files)} supported files")
        return files

    def convert_text_to_pdf(self, text_file: Path) -> Optional[Path]:
        """Convert text file to PDF using reportlab."""
        if not REPORTLAB_AVAILABLE:
            logging.error(f"[{self.client_id}] reportlab not available for text conversion")
            return None

        try:
            output_path = Path(self.temp_dir) / f"{text_file.stem}.pdf"

            # Read text content
            with open(text_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Create PDF
            doc = SimpleDocTemplate(str(output_path), pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            # Add title
            title = Paragraph(f"<b>{text_file.name}</b>", styles['Title'])
            story.append(title)
            story.append(Spacer(1, 12))

            # Add content (split by paragraphs)
            for para in content.split('\n\n'):
                if para.strip():
                    p = Paragraph(para.replace('\n', '<br/>'), styles['BodyText'])
                    story.append(p)
                    story.append(Spacer(1, 6))

            doc.build(story)
            logging.info(f"[{self.client_id}] Converted text: {text_file.name} -> {output_path.name}")
            return output_path

        except Exception as e:
            logging.error(f"[{self.client_id}] Text conversion failed for {text_file.name}: {e}")
            return None

    def convert_csv_to_pdf(self, csv_file: Path) -> Optional[Path]:
        """Convert CSV to PDF table using reportlab."""
        if not REPORTLAB_AVAILABLE or not PANDAS_AVAILABLE:
            logging.error(f"[{self.client_id}] Missing dependencies for CSV conversion")
            return None

        try:
            output_path = Path(self.temp_dir) / f"{csv_file.stem}.pdf"

            # Read CSV
            df = pd.read_csv(csv_file, encoding='utf-8', errors='ignore')

            # Limit rows for PDF (too large tables won't fit)
            if len(df) > 100:
                logging.warning(f"[{self.client_id}] CSV has {len(df)} rows, limiting to first 100")
                df = df.head(100)

            # Create PDF
            doc = SimpleDocTemplate(str(output_path), pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            # Add title
            title = Paragraph(f"<b>{csv_file.name}</b>", styles['Title'])
            story.append(title)
            story.append(Spacer(1, 12))

            # Convert DataFrame to table data
            data = [df.columns.tolist()] + df.values.tolist()

            # Create table
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            story.append(table)
            doc.build(story)

            logging.info(f"[{self.client_id}] Converted CSV: {csv_file.name} -> {output_path.name}")
            return output_path

        except Exception as e:
            logging.error(f"[{self.client_id}] CSV conversion failed for {csv_file.name}: {e}")
            return None

    def convert_image_to_pdf(self, image_file: Path) -> Optional[Path]:
        """Convert image to PDF using Pillow and reportlab."""
        if not PIL_AVAILABLE or not REPORTLAB_AVAILABLE:
            logging.error(f"[{self.client_id}] Missing dependencies for image conversion")
            return None

        try:
            output_path = Path(self.temp_dir) / f"{image_file.stem}.pdf"

            # Open and convert image
            img = Image.open(image_file)

            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Save as PDF
            img.save(str(output_path), 'PDF', resolution=100.0)

            logging.info(f"[{self.client_id}] Converted image: {image_file.name} -> {output_path.name}")
            return output_path

        except Exception as e:
            logging.error(f"[{self.client_id}] Image conversion failed for {image_file.name}: {e}")
            return None

    def convert_docx_to_pdf(self, docx_file: Path) -> Optional[Path]:
        """Convert DOCX to PDF using LibreOffice (system command)."""
        try:
            output_path = Path(self.temp_dir) / f"{docx_file.stem}.pdf"

            # Try LibreOffice conversion (most reliable)
            result = subprocess.run(
                ['soffice', '--headless', '--convert-to', 'pdf', '--outdir',
                 self.temp_dir, str(docx_file)],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0 and output_path.exists():
                logging.info(f"[{self.client_id}] Converted DOCX: {docx_file.name} -> {output_path.name}")
                return output_path
            else:
                logging.warning(f"[{self.client_id}] LibreOffice conversion failed, trying fallback")
                return self._convert_docx_fallback(docx_file)

        except FileNotFoundError:
            logging.warning(f"[{self.client_id}] LibreOffice not found, using fallback")
            return self._convert_docx_fallback(docx_file)
        except Exception as e:
            logging.error(f"[{self.client_id}] DOCX conversion failed for {docx_file.name}: {e}")
            return None

    def _convert_docx_fallback(self, docx_file: Path) -> Optional[Path]:
        """Fallback DOCX conversion using python-docx + reportlab."""
        if not DOCX_AVAILABLE or not REPORTLAB_AVAILABLE:
            logging.error(f"[{self.client_id}] Missing dependencies for DOCX fallback")
            return None

        try:
            output_path = Path(self.temp_dir) / f"{docx_file.stem}.pdf"

            # Read DOCX
            doc = Document(docx_file)

            # Create PDF
            pdf_doc = SimpleDocTemplate(str(output_path), pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            # Add title
            title = Paragraph(f"<b>{docx_file.name}</b>", styles['Title'])
            story.append(title)
            story.append(Spacer(1, 12))

            # Add paragraphs
            for para in doc.paragraphs:
                if para.text.strip():
                    p = Paragraph(para.text, styles['BodyText'])
                    story.append(p)
                    story.append(Spacer(1, 6))

            pdf_doc.build(story)
            logging.info(f"[{self.client_id}] Converted DOCX (fallback): {docx_file.name}")
            return output_path

        except Exception as e:
            logging.error(f"[{self.client_id}] DOCX fallback failed for {docx_file.name}: {e}")
            return None

    def convert_file_to_pdf(self, file_path: Path) -> Optional[Path]:
        """
        Convert any supported file to PDF.

        Args:
            file_path: Path to file to convert

        Returns:
            Path to converted PDF or None if failed
        """
        ext = file_path.suffix.lower()

        # Already PDF - just copy
        if ext == '.pdf':
            dest_path = Path(self.temp_dir) / file_path.name
            shutil.copy2(file_path, dest_path)
            logging.info(f"[{self.client_id}] Copied existing PDF: {file_path.name}")
            return dest_path

        # Text files
        elif ext in {'.txt', '.md'}:
            return self.convert_text_to_pdf(file_path)

        # CSV files
        elif ext == '.csv':
            return self.convert_csv_to_pdf(file_path)

        # Images
        elif ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}:
            return self.convert_image_to_pdf(file_path)

        # DOCX files
        elif ext == '.docx':
            return self.convert_docx_to_pdf(file_path)

        # Excel files (convert via pandas)
        elif ext in {'.xlsx', '.xls'} and PANDAS_AVAILABLE and REPORTLAB_AVAILABLE:
            # Treat like CSV - read first sheet and convert
            try:
                temp_csv = Path(self.temp_dir) / f"{file_path.stem}.csv"
                df = pd.read_excel(file_path)
                df.to_csv(temp_csv, index=False)
                return self.convert_csv_to_pdf(temp_csv)
            except Exception as e:
                logging.error(f"[{self.client_id}] Excel conversion failed: {e}")
                return None

        else:
            logging.warning(f"[{self.client_id}] Unsupported file type: {file_path.name}")
            return None

    def concatenate_pdfs(self, pdf_files: List[Path], output_path: Path) -> bool:
        """
        Concatenate multiple PDFs into one.

        Args:
            pdf_files: List of PDF file paths to merge
            output_path: Path for output concatenated PDF

        Returns:
            True if successful, False otherwise
        """
        if not PYPDF2_AVAILABLE:
            logging.error(f"[{self.client_id}] PyPDF2/pypdf not available for concatenation")
            return False

        if not pdf_files:
            logging.error(f"[{self.client_id}] No PDF files to concatenate")
            return False

        try:
            # Handle different pypdf versions
            if PYPDF_VERSION == 2:
                # PyPDF2 uses PdfMerger
                merger = PdfMerger()
                for pdf_file in pdf_files:
                    try:
                        PdfReader(str(pdf_file))
                        merger.append(str(pdf_file))
                        logging.debug(f"[{self.client_id}] Added to merge: {pdf_file.name}")
                    except Exception as e:
                        logging.warning(f"[{self.client_id}] Skipping invalid PDF {pdf_file.name}: {e}")
                merger.write(str(output_path))
                merger.close()
            else:
                # pypdf 3.x+ uses PdfWriter
                writer = PdfWriter()
                for pdf_file in pdf_files:
                    try:
                        reader = PdfReader(str(pdf_file))
                        writer.append(reader)
                        logging.debug(f"[{self.client_id}] Added to merge: {pdf_file.name}")
                    except Exception as e:
                        logging.warning(f"[{self.client_id}] Skipping invalid PDF {pdf_file.name}: {e}")
                with open(str(output_path), 'wb') as output_file:
                    writer.write(output_file)

            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            logging.info(f"[{self.client_id}] Created consolidated PDF: {output_path.name} ({file_size_mb:.2f} MB)")
            return True

        except Exception as e:
            logging.error(f"[{self.client_id}] PDF concatenation failed: {e}")
            return False

    def consolidate(self) -> Optional[Path]:
        """
        Main method: Convert all files and create consolidated PDF.

        Returns:
            Path to consolidated {client}-One.pdf or None if failed
        """
        logging.info(f"[{self.client_id}] Starting PDF consolidation for folder: {self.client_folder}")

        # Find all source files
        source_files = self.find_source_files()
        if not source_files:
            logging.warning(f"[{self.client_id}] No files found to consolidate")
            return None

        # Convert each file to PDF
        converted_pdfs = []
        for source_file in source_files:
            logging.info(f"[{self.client_id}] Converting: {source_file.name}")
            pdf_path = self.convert_file_to_pdf(source_file)
            if pdf_path and pdf_path.exists():
                converted_pdfs.append(pdf_path)
            else:
                logging.warning(f"[{self.client_id}] Failed to convert: {source_file.name}")

        if not converted_pdfs:
            logging.error(f"[{self.client_id}] No files successfully converted to PDF")
            return None

        logging.info(f"[{self.client_id}] Successfully converted {len(converted_pdfs)}/{len(source_files)} files")

        # Create output filename
        output_filename = f"{self.client_id}-One.pdf"
        output_path = self.client_folder / output_filename

        # Concatenate all PDFs
        if self.concatenate_pdfs(converted_pdfs, output_path):
            logging.info(f"[{self.client_id}] ✓ Consolidation complete: {output_path}")
            return output_path
        else:
            logging.error(f"[{self.client_id}] ✗ Consolidation failed")
            return None


def consolidate_client_pdfs(client_id: str, client_folder: str) -> Tuple[bool, Optional[Path]]:
    """
    Convenience function to consolidate all files for a client into one PDF.

    Args:
        client_id: Client identifier (e.g., 'merck_test')
        client_folder: Path to client's source folder

    Returns:
        Tuple of (success: bool, pdf_path: Optional[Path])

    Example:
        success, pdf_path = consolidate_client_pdfs('merck_test', '/path/to/Merck/')
        if success:
            print(f"Created: {pdf_path}")
    """
    try:
        with PDFConsolidator(client_id, client_folder) as consolidator:
            pdf_path = consolidator.consolidate()
            return (pdf_path is not None, pdf_path)
    except Exception as e:
        logging.error(f"[{client_id}] Consolidation error: {e}")
        return (False, None)


if __name__ == "__main__":
    # Test the consolidator
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    # Example usage
    test_client = "merck_test"
    test_folder = "/Users/jasona/account_planning/Venella_2026/Merck/"

    success, pdf_path = consolidate_client_pdfs(test_client, test_folder)
    if success:
        print(f"\n✓ Success! Created: {pdf_path}")
    else:
        print(f"\n✗ Failed to consolidate PDFs for {test_client}")
