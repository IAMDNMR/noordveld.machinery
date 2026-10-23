from app.design_studio.frontend_repair import build_errors, patch_file
from app.design_studio.frontend_generation import errors_for, clean_source, build_source, FrontendGenerationError, merge_module_repair, module_contracts
import pytest


def test_no_op_patch_is_not_reported_as_a_repair():
    class Model:
        def studio_frontend(self, *_):
            return {"edits": [{"find": "const broken = true", "replace": "const broken = true"}]}

    files = {"src/App.tsx": "const broken = true"}
    assert not patch_file(Model(), files, "src/App.tsx", [{"line": 1, "message": "broken"}])


def test_diagnostics_keep_later_files_after_large_first_file_report():
    report = "\n".join(
        f"src/App.tsx({i},1): error TS2322: " + "x" * 100 for i in range(1, 90)
    )
    report += "\nsrc/pages/Request.tsx(8,2): error TS2322: wrong props"
    assert "src/pages/Request.tsx" in build_errors(report)
    assert "wrong props" in errors_for(report, "src/pages/Request.tsx")
    # The same report as the Linux builder prints it (only the climb out of the working directory is left in front of src/),
    # and as Windows prints it (the temporary folder's name is still there): both give the file and its line.
    for path in ("../../../../../../src/App.tsx", "../../Temp/studio-source-check-ab12/src/App.tsx"):
        found = build_errors(f"{path}(1,42): error TS2304: Cannot find name 'missingName'.")
        assert found["src/App.tsx"][0]["line"] == 1, path


def test_valid_patch_preserves_other_source():
    class Model:
        def studio_frontend(self, *_):
            return {"edits": [{"find": "const label = 1", "replace": "const label = 'Request'"}]}

    files = {"src/App.tsx": "const label = 1\nexport default function App(){return <h1>{label}</h1>}"}
    assert patch_file(Model(), files, "src/App.tsx", [{"line": 1, "message": "wrong type"}])
    assert files["src/App.tsx"].endswith("export default function App(){return <h1>{label}</h1>}")


@pytest.mark.parametrize('response', [None, [], 'raw source', {'edits': 'code'}, {'edits': ['replace this', None, 42, []]}])
def test_malformed_model_edits_fall_back_to_rewrite_without_crashing(response):
    class Model:
        def studio_frontend(self, *_):
            return response
    files = {'src/App.tsx': 'const label = 1'}
    assert not patch_file(Model(), files, 'src/App.tsx', [{'line': 1, 'message': 'wrong type'}])
    assert files['src/App.tsx'] == 'const label = 1'


def test_ambiguous_patch_never_replaces_every_occurrence():
    class Model:
        def studio_frontend(self, *_):
            return {'edits': [{'find': 'value', 'replace': 'other'}]}
    files = {'src/App.tsx': 'const value = {value: 1}'}
    assert not patch_file(Model(), files, 'src/App.tsx', [{'line': 1, 'message': 'wrong type'}])
    assert files['src/App.tsx'] == 'const value = {value: 1}'


def test_source_wrappers_are_unwrapped_only_for_the_requested_file():
    import json
    source = 'export default function App(){return <main>Service</main>}'
    assert clean_source('```tsx\n' + source + '\n```', 'src/App.tsx') == source
    for key in ('source', 'content', 'code'):
        assert clean_source(json.dumps({'file': 'src/App.tsx', key: source}), 'src/App.tsx') == source
    wrong = json.dumps({'file': 'src/Other.tsx', 'source': source})
    assert clean_source(wrong, 'src/App.tsx') == wrong
    edits = json.dumps({'edits': [{'find': 'a', 'replace': 'b'}]})
    assert clean_source(edits, 'src/App.tsx') == edits


def test_build_rejects_a_hook_inside_an_event_handler_before_runtime():
    files = {
        'src/App.tsx': "import {useStudio} from '@studio/sdk'; export default function App(){const click=()=>{const {refresh}=useStudio(); void refresh()}; return <button onClick={click}>Refresh</button>}",
        'src/styles.css': 'body{margin:0}',
    }
    with pytest.raises(FrontendGenerationError, match='(?i)hook') as failure:
        build_source(files)
    assert 'src/App.tsx' in str(failure.value)
    assert build_errors(str(failure.value))['src/App.tsx'][0]['line'] == 1


def test_export_repairs_never_concatenate_a_returned_full_module():
    original = 'export default function Panel(){return null}'
    replacement = original + '\nexport function Helper(){return null}'
    assert merge_module_repair(original, replacement, 'src/Panel.tsx', {'Helper'}) == replacement
    suffix = 'export function Helper(){return null}'
    assert merge_module_repair(original, suffix, 'src/Panel.tsx', {'Helper'}).count('function Panel') == 1
    assert merge_module_repair(original, 'export function Other(){}', 'src/Panel.tsx', {'Helper'}) is None
    named_original = original + '\nexport function Existing(){}'
    assert merge_module_repair(named_original, 'export default function Other(){}\n' + suffix, 'src/Panel.tsx', {'Helper'}) is None
    alias = 'export { Panel };'
    assert merge_module_repair(original, alias, 'src/Panel.tsx', {'Panel'}) == original + '\n\n' + alias + '\n'
    from app.design_studio.frontend_imports import exports
    assert exports(original) == set()
    assert exports(original + '\n' + alias) == {'Panel'}


def test_file_writers_receive_actual_component_props_without_implementation_bodies():
    contracts = module_contracts({'src/Nav.tsx': '''
interface Props { activePage: string; onNavigate: (page: string) => void }
export default function Nav({activePage, onNavigate}: Props) {
  const privateImplementation = 'must not be included';
  return <button onClick={() => onNavigate(activePage)}>Open</button>
}
export const label = (id: string): string => id.toUpperCase();
'''})
    contract = contracts['src/Nav.tsx']
    assert 'onNavigate: (page: string) => void' in contract
    assert 'Nav({activePage, onNavigate}: Props)' in contract
    assert 'id: string' in contract
    assert 'privateImplementation' not in contract and 'toUpperCase' not in contract
    assert module_contracts({'src/Stub.tsx': '// Implement the top bar here'})['src/Stub.tsx'] == ''


def test_self_reexport_cannot_hide_a_missing_component():
    with pytest.raises(FrontendGenerationError, match='cannot import or re-export itself'):
        build_source({'src/App.tsx': "export {default} from './App'", 'src/styles.css': 'body{margin:0}'})
