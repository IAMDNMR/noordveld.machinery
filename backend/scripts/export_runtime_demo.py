"""Export the explicitly synthetic TMS application into a NEW temporary directory."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.design_studio.compiler import compile_project
from app.design_studio.runtime_demo import synthetic_transport
from app.design_studio.knowledge.provider import LocalKnowledgeProvider
from app.domain_knowledge.store import ReadOnlyDomainStore

result = compile_project(synthetic_transport(), ReadOnlyDomainStore(), LocalKnowledgeProvider())
if result['status'] != 'generated':
    raise RuntimeError('Synthetic fixture failed compiler checks')
directory = Path(tempfile.mkdtemp(prefix='studio-runtime-build-'))
for name, content in result['files'].items():
    output = directory / name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
print(directory)
