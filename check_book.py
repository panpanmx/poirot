import pypdf
reader = pypdf.PdfReader("book.pdf")
print("Total:", len(reader.pages))
for i, p in enumerate(reader.pages):
    t = p.extract_text() or ""
    if "wikipedia" in t.lower():
        print(f"Found on page {i+1}:")
        print(t)
