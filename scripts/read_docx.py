"""Utility to read docx files for founder data extraction."""
import sys
from docx import Document

path = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 99999

doc = Document(path)
text = '\n'.join(p.text for p in doc.paragraphs)
print(text[:limit])
print(f'\n\n=== TOTAL: {len(text)} chars, {len(text.split())} words ===')
