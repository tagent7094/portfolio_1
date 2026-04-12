"""Extract all post content from docx table format."""
import sys, json, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
from docx import Document

path = sys.argv[1]
out_path = sys.argv[2] if len(sys.argv) > 2 else None
doc = Document(path)

posts = []
for table in doc.tables:
    headers = [c.text.strip().lower() for c in table.rows[0].cells]
    for row in table.rows[1:]:
        cells = [c.text.strip() for c in row.cells]
        post = {}
        for i, h in enumerate(headers):
            if i < len(cells):
                post[h] = cells[i]
        if post.get('posts', '').strip():
            posts.append(post)

# Print all posts
for i, p in enumerate(posts):
    text = p.get('posts', '')
    likes = p.get('likes', '')
    comments = p.get('comments', '')
    reposts = p.get('reposts', '')
    print(f"--- POST {i+1} (likes={likes}, comments={comments}, reposts={reposts}) ---")
    print(text[:2000])
    print()

print(f"\n=== TOTAL: {len(posts)} posts ===")
total_chars = sum(len(p.get('posts','')) for p in posts)
print(f"=== {total_chars} total characters ===")

if out_path:
    with open(out_path, 'w', encoding='utf-8') as f:
        for i, p in enumerate(posts):
            f.write(f"--- POST {i+1} ---\n")
            f.write(p.get('posts', '') + '\n\n')
    print(f"Saved to {out_path}")
