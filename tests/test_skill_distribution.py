from __future__ import annotations

import copy
from pathlib import Path

import pytest

import tools.skills_governance as governance
from tools.skills_governance import (
    ValidationReport,
    SelectedSkill,
    export_projection,
    load_manifest,
    main,
    select_skills,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _selected_ids(audience: str) -> tuple[str, ...]:
    return tuple(skill.skill_id for skill in select_skills(REPO_ROOT, audience=audience))


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob('*'))
        if path.is_file()
    }


@pytest.mark.parametrize('audience', ['development', 'operation'])
def test_selection_is_sorted_active_normal_and_audience_aware(audience: str) -> None:
    manifest = load_manifest(REPO_ROOT)
    expected = tuple(
        sorted(
            entry['id']
            for entry in manifest['skills']
            if entry['lifecycle'] == 'active'
            and entry['distribution']['mode'] == 'normal'
            and audience in entry['distribution']['audiences']
        )
    )

    selected = _selected_ids(audience)

    assert selected == expected
    assert 'network-autofix' not in selected


def test_selection_honors_explicit_mode_without_admitting_planned_or_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = copy.deepcopy(load_manifest(REPO_ROOT))
    by_id = {entry['id']: entry for entry in manifest['skills']}
    by_id['enterprise-configuration']['distribution']['mode'] = 'explicit_only'
    by_id['enterprise-services']['lifecycle'] = 'planned'
    by_id['enterprise-services']['distribution']['mode'] = 'explicit_only'
    by_id['enterprise-voice']['lifecycle'] = 'retired'
    by_id['enterprise-voice']['distribution']['mode'] = 'explicit_only'
    by_id['enterprise-security']['lifecycle'] = 'deprecated'
    by_id['enterprise-security']['distribution']['mode'] = 'explicit_only'
    monkeypatch.setattr(
        governance,
        'load_manifest',
        lambda repo_root, manifest_path=None: copy.deepcopy(manifest),
    )

    normal = {
        skill.skill_id
        for skill in governance.select_skills(REPO_ROOT, audience='operation')
    }
    explicit = {
        skill.skill_id
        for skill in governance.select_skills(
            REPO_ROOT,
            audience='operation',
            include_explicit=True,
        )
    }

    assert 'enterprise-configuration' not in normal
    assert 'enterprise-security' not in normal
    assert {'enterprise-configuration', 'enterprise-security'} <= explicit
    assert 'enterprise-services' not in explicit
    assert 'enterprise-voice' not in explicit


def test_selection_validates_and_uses_one_manifest_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_manifest = copy.deepcopy(load_manifest(REPO_ROOT))
    changed_manifest = copy.deepcopy(valid_manifest)
    changed_manifest['skills'][0]['path'] = '../../skill/SKILL.md'
    calls = 0

    def changing_manifest(repo_root: Path, manifest_path: Path | None = None):
        nonlocal calls
        calls += 1
        return copy.deepcopy(valid_manifest if calls == 1 else changed_manifest)

    monkeypatch.setattr(governance, 'load_manifest', changing_manifest)

    selected = governance.select_skills(REPO_ROOT, audience='operation')

    assert calls == 1
    assert all(skill.canonical_path.startswith('skills/') for skill in selected)


@pytest.mark.parametrize(
    ('client', 'expects_adapter'),
    [('portable', False), ('claude', False), ('openai', True)],
)
def test_export_projection_contains_only_selected_canonical_resources(
    tmp_path: Path,
    client: str,
    expects_adapter: bool,
) -> None:
    destination = tmp_path / client

    selected = export_projection(
        REPO_ROOT,
        destination,
        audience='operation',
        client=client,
    )

    assert destination.is_dir()
    assert not (destination / 'skill').exists()
    assert not (destination / 'skills' / 'network-autofix').exists()
    for skill in selected:
        projected = destination / Path(skill.canonical_path).parent
        assert (projected / 'SKILL.md').is_file()
        adapter = projected / 'agents' / 'openai.yaml'
        assert adapter.is_file() is expects_adapter
        agent_files = (
            sorted(path.relative_to(projected).as_posix() for path in projected.rglob('agents/*'))
            if (projected / 'agents').exists()
            else []
        )
        assert agent_files == (['agents/openai.yaml'] if expects_adapter else [])

    for relative, payload in _tree_snapshot(destination).items():
        assert relative.startswith('skills/')
        assert (REPO_ROOT / relative).read_bytes() == payload


def test_export_is_reproducible(tmp_path: Path) -> None:
    first = tmp_path / 'first'
    second = tmp_path / 'second'

    export_projection(REPO_ROOT, first, audience='development', client='openai')
    export_projection(REPO_ROOT, second, audience='development', client='openai')

    assert _tree_snapshot(first) == _tree_snapshot(second)


def test_export_rejects_existing_destination_without_changing_it(tmp_path: Path) -> None:
    destination = tmp_path / 'existing'
    destination.mkdir()
    marker = destination / 'keep.txt'
    marker.write_text('keep', encoding='utf-8')

    with pytest.raises(FileExistsError, match='already exists'):
        export_projection(
            REPO_ROOT,
            destination,
            audience='operation',
            client='portable',
        )

    assert marker.read_text(encoding='utf-8') == 'keep'


@pytest.mark.parametrize(
    ('audience', 'client'),
    [('invalid', 'portable'), ('operation', 'invalid')],
)
def test_export_argument_failure_leaves_no_destination(
    tmp_path: Path,
    audience: str,
    client: str,
) -> None:
    destination = tmp_path / 'projection'

    with pytest.raises(ValueError):
        export_projection(
            REPO_ROOT,
            destination,
            audience=audience,
            client=client,
        )

    assert not destination.exists()


def test_export_validation_failure_leaves_no_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / 'projection'
    monkeypatch.setattr(
        governance,
        'validate_skill_governance',
        lambda repo_root, manifest_path=None, *, manifest_data=None: ValidationReport(
            errors=('invalid manifest',), metrics=()
        ),
    )

    with pytest.raises(ValueError, match='invalid manifest'):
        governance.export_projection(
            REPO_ROOT,
            destination,
            audience='operation',
            client='portable',
        )

    assert not destination.exists()


def test_export_rejects_projection_source_outside_canonical_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / 'projection'
    malicious = SelectedSkill(
        skill_id='campus-layer2',
        canonical_path='../../skill/SKILL.md',
        lifecycle='active',
        distribution_mode='normal',
        audiences=('operation',),
    )
    monkeypatch.setattr(governance, 'select_skills', lambda *args, **kwargs: (malicious,))

    with pytest.raises(ValueError, match='escapes skills'):
        governance.export_projection(
            REPO_ROOT,
            destination,
            audience='operation',
            client='portable',
        )

    assert not destination.exists()


@pytest.mark.parametrize('symlink_kind', ['skill_root', 'adapter'])
def test_export_rejects_symlinked_canonical_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symlink_kind: str,
) -> None:
    destination = tmp_path / symlink_kind
    skill_root = REPO_ROOT / 'skills' / 'campus-layer2'
    simulated_symlink = (
        skill_root
        if symlink_kind == 'skill_root'
        else skill_root / 'agents' / 'openai.yaml'
    )
    original_is_symlink = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == simulated_symlink or original_is_symlink(path)

    monkeypatch.setattr(Path, 'is_symlink', is_symlink)

    with pytest.raises(ValueError, match='does not support symlinks'):
        governance.export_projection(
            REPO_ROOT,
            destination,
            audience='operation',
            client='openai',
        )

    assert not destination.exists()


def test_export_rejects_descendant_reparse_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / 'projection'
    simulated_junction = REPO_ROOT / 'skills' / 'campus-layer2' / 'agents'
    outside = tmp_path / 'outside'
    outside.mkdir()
    original_resolve = Path.resolve

    def resolve(path: Path, strict: bool = False) -> Path:
        if path == simulated_junction:
            return outside
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, 'resolve', resolve)

    with pytest.raises(ValueError, match='escapes canonical Skill'):
        governance.export_projection(
            REPO_ROOT,
            destination,
            audience='operation',
            client='portable',
        )

    assert not destination.exists()


def test_export_cli_uses_explicit_staging_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / 'cli-projection'
    monkeypatch.chdir(REPO_ROOT)

    result = main(
        [
            'export',
            '--destination',
            str(destination),
            '--audience',
            'operation',
            '--client',
            'portable',
        ]
    )

    assert result == 0
    assert destination.is_dir()
    assert 'SKILL_EXPORT=PASS' in capsys.readouterr().out


def test_validate_metrics_and_legacy_cli_modes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)

    assert main([]) == 0
    assert 'SKILL_GOVERNANCE=PASS' in capsys.readouterr().out
    assert main(['validate']) == 0
    assert 'SKILL_GOVERNANCE=PASS' in capsys.readouterr().out
    assert main(['metrics']) == 0
    assert 'CONTEXT_METRICS' in capsys.readouterr().out
