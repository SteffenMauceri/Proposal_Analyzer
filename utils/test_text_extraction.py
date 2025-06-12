#!/usr/bin/env python3
"""
Simple test script for text extraction functionality.
"""

from pathlib import Path
from text_extraction import extract_text_from_document

def test_text_extraction():
    """Test text extraction from various document formats."""
    
    # Test directories that might contain sample documents
    test_dirs = [
        Path("../data/call"),
        Path("../data/proposal"),
        Path("../tests/data")
    ]
    
    print("Testing text extraction functionality...")
    print("=" * 50)
    
    # Look for any document files in the test directories
    supported_extensions = ['.pdf', '.doc', '.docx']
    found_files = []
    
    for test_dir in test_dirs:
        if test_dir.exists():
            for ext in supported_extensions:
                files = list(test_dir.glob(f"*{ext}"))
                found_files.extend(files)
    
    if not found_files:
        print("No test documents found in common directories.")
        print("To test, place a PDF, DOC, or DOCX file in data/call/ or data/proposal/")
        return
    
    for file_path in found_files[:3]:  # Test up to 3 files
        print(f"\nTesting: {file_path.name} ({file_path.suffix})")
        print("-" * 30)
        
        try:
            extracted_text = extract_text_from_document(file_path)
            
            if extracted_text:
                # Show first 200 characters of extracted text
                preview = extracted_text[:200]
                if len(extracted_text) > 200:
                    preview += "..."
                
                print(f"✓ Successfully extracted {len(extracted_text)} characters")
                print(f"Preview: {preview}")
            else:
                print("✗ No text extracted (file may be empty or unsupported)")
                
        except Exception as e:
            print(f"✗ Error extracting text: {e}")
    
    print(f"\nTest completed. Checked {len(found_files)} file(s).")

if __name__ == "__main__":
    test_text_extraction() 