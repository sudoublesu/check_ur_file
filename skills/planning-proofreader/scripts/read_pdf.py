#!/usr/bin/env python3
"""
read_pdf.py - 从 .pdf 文件提取文本内容

Usage:
    python read_pdf.py <file.pdf> [output.json]

Output JSON 结构:
{
  "file": "filename.pdf",
  "total_pages": 10,
  "pages": [
    {"page": 1, "text": "页面文本..."}
  ],
  "full_text": "全部文本拼接..."
}
"""

import sys
import json
import fitz  # PyMuPDF


def extract_pdf(path: str) -> dict:
    doc = fitz.open(path)
    pages = []
    full_parts = []

    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        pages.append({"page": i + 1, "text": text})
        full_parts.append(text)

    return {
        "file": path,
        "total_pages": len(doc),
        "pages": pages,
        "full_text": "\n\n".join(full_parts),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python read_pdf.py <file.pdf> [output.json]", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    data = extract_pdf(path)

    if len(sys.argv) >= 3:
        with open(sys.argv[2], 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已输出到 {sys.argv[2]}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
