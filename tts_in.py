import pymupdf
from collections import Counter

BOOK = "Inference Engineering.pdf"
doc = pymupdf.open(BOOK)

toc = doc.get_toc()
print(f"pages: {doc.page_count}, toc entries: {len(toc)}\n")
for level, title, page in toc:
    if level == 1:
        print(f"  {title!r:45} -> page {page}")

print("\nfont-size histogram (weighted by chars):")
sizes = Counter()
for pno in range(doc.page_count):
    for block in doc[pno].get_text("dict")["blocks"]:
        if block["type"] != 0:  # skip image blocks
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                txt = span["text"].strip()
                if txt:
                    sizes[round(span["size"], 1)] += len(txt)
for size, n in sizes.most_common(15):
    print(f"  {size:6.1f} pt  {n:8d} chars")
