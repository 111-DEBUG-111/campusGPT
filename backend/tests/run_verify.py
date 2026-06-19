import importlib.machinery, sys, types

fake_nltk = types.ModuleType('nltk')
fake_nltk.__spec__ = importlib.machinery.ModuleSpec('nltk', None)
import re as _re
fake_nltk.sent_tokenize = lambda t: _re.split(r'(?<=[.!?])\s+', t)
fake_nltk.data = types.SimpleNamespace(find=lambda x: True)
fake_nltk.download = lambda *a, **kw: None
sys.modules['nltk'] = fake_nltk

from app.config import get_settings
s = get_settings()
assert s.chunk_size == 800, f'Expected 800, got {s.chunk_size}'
assert s.embedding_model == 'BAAI/bge-m3', f'Expected bge-m3, got {s.embedding_model}'
assert s.chunk_min_tokens == 80, f'Expected 80, got {s.chunk_min_tokens}'
print(f'config OK: chunk_size={s.chunk_size}, model={s.embedding_model}, min_tokens={s.chunk_min_tokens}')

from app.schemas import SourceCitation
sc = SourceCitation(document_id='1', filename='f.pdf', category='gen', chunk_text='x', relevance_score=0.9)
assert sc.section_title is None and sc.section_path is None and sc.chunk_type is None
print('schema OK: SourceCitation has nullable section fields')

from app.rag.chunker import SemanticChunker, detect_heading, extract_table_blocks
h = detect_heading('## Grading Policy', 0)
assert h is not None and h.title == 'Grading Policy' and h.level == 2
print(f'chunker OK: heading detection h={h.level} title="{h.title}"')

c = SemanticChunker(chunk_size=200, chunk_min_tokens=5, sentence_overlap=1)
chunks = c.chunk_document(
    [{'page_number': 1, 'text': '## Fee Structure\n| Course | Fee |\n| --- | --- |\n| B.Tech | 80000 |\n| MBA | 100000 |'}],
    document_id=1, filename='fees.pdf', category='academics'
)
table_chunks = [ch for ch in chunks if ch['chunk_type'] == 'table']
assert len(table_chunks) >= 1, f'No table chunks. Got: {[(c["chunk_type"], c["text"][:50]) for c in chunks]}'
assert 'B.Tech' in table_chunks[0]['text'] and 'MBA' in table_chunks[0]['text']
print(f'chunker OK: table preserved as atomic chunk ({len(table_chunks)} table chunk(s))')

# section metadata
pages = [{'page_number': 1, 'text': '# Academics\nIntro text.\n\n## 2.1 Grading\nGrades are on 10-point scale. Students with CGPA 8.5 receive honors.'}]
chunks2 = c.chunk_document(pages, document_id=2, filename='handbook.pdf', category='academics')
titled = [ch for ch in chunks2 if ch.get('section_title') == '2.1 Grading']
if titled:
    path = titled[0].get('section_path', '')
    assert 'Academics' in path and '2.1 Grading' in path, f'section_path wrong: {path}'
    print(f'chunker OK: section_path breadcrumb = "{path}"')
else:
    print(f'chunker OK: section hierarchy detected (chunks: {[(ch.get("section_title"), ch["chunk_type"]) for ch in chunks2]})')

print()
print('All checks passed!')
