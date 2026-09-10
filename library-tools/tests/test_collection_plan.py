"""Guard the new planner's history, reproducibility and non-approval boundaries."""
import hashlib
import importlib
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from librarytools.find import Query
from librarytools.inventory import LibraryDatabase, scan_library


def planner():
    return importlib.import_module('librarytools.collection_plan')


@pytest.fixture
def library(tmp_path):
    root = tmp_path / 'samples'
    root.mkdir()
    paths = []
    for index in range(12):
        path = root / 'PACKS' / 'tribal-pack' / f'perc-tribal-{index:02}.wav'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'unique source {index}'.encode())
        paths.append(path)
    alias = root / 'CURATED' / 'PERC' / 'renamed-favourite.wav'
    alias.parent.mkdir(parents=True)
    shutil.copy2(paths[0], alias)
    db = LibraryDatabase(root / '.eidetic' / 'library.sqlite')
    db.bind_root(root)
    scan_library(root, db)
    ids = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    history = tmp_path / 'previous.json'
    history.write_text(json.dumps({
        'schema': 'eidetic-delegated-library-v1',
        'items': [{'device': 'octatrack', 'sample_id': sample_id,
                   'output_sha256': 'f' * 64} for sample_id in ids[:3]],
    }))
    return root, db, ids, history


def create(library, **changes):
    root, _, _, history = library
    options = dict(device='octatrack', count=5, freshness='exclude',
                   query=Query(terms=('tribal', 'perc')), brief='hypnotic tribal',
                   seed=10, history_paths=[history])
    options.update(changes)
    return planner().create_plan(root, **options)


def selected(plan):
    return [row['sample_id'] for row in plan['selected']]


def test_exclusion_deduplicates_aliases_and_reports_shortage_without_refilling(library):
    plan = create(library, count=12)
    assert len(plan['snapshot']['candidates']) == 12
    assert len(selected(plan)) == len(set(selected(plan))) == 9
    assert set(selected(plan)).isdisjoint(library[2][:3])
    assert plan['summary']['shortage'] == 3
    assert plan['summary']['known_repeats'] == 0
    assert all(row['decision'] == 'unreviewed' for row in plan['selected'])


def test_original_alias_can_match_after_curated_copy_becomes_preferred(library):
    plan = create(library, count=12, freshness='allow')
    first = next(row for row in plan['snapshot']['candidates'] if row['sample_id'] == library[2][0])
    assert len(first['aliases']) == 2
    assert any(alias['path'].endswith('perc-tribal-00.wav') for alias in first['aliases'])
    assert library[2][0] in selected(plan)


def test_prefer_new_orders_known_repeats_after_unseen_in_supplied_history(library):
    plan = create(library, count=12, freshness='prefer-new')
    assert set(selected(plan)[:9]).isdisjoint(library[2][:3])
    assert set(selected(plan)[9:]) == set(library[2][:3])
    assert plan['summary']['known_repeats'] == 3


def test_unknown_history_is_not_presented_as_never_exported(library):
    with pytest.raises(ValueError, match='history'):
        create(library, history_paths=[])
    plan = create(library, history_paths=[], freshness='allow')
    assert plan['history']['coverage'] == 'unknown'
    assert all(row['history_status'] == 'unknown' for row in plan['selected'])


def test_same_snapshot_and_seed_reproduce_selection_but_new_seed_changes_it(library):
    first = create(library)
    assert selected(first) == selected(create(library))
    assert first['plan_id'] == create(library)['plan_id']
    rerun = planner().regenerate_plan(first, seed=10)
    assert selected(rerun) == selected(first)
    assert selected(planner().regenerate_plan(first, seed=20)) != selected(first)
    assert rerun['parent_plan_id'] == first['plan_id']


def test_pins_survive_multiple_offline_generations_and_do_not_grant_approval(library):
    first = create(library)
    pin = selected(first)[0]
    shutil.rmtree(library[0])
    library[3].unlink()
    second = planner().regenerate_plan(first, seed=20, pins=[pin])
    third = planner().regenerate_plan(second, seed=30)
    assert pin in selected(second) and pin in selected(third)
    assert third['pins'] == [pin]
    assert third['snapshot'] == first['snapshot']
    assert all(row['decision'] == 'unreviewed' for row in third['selected'])


def test_pins_must_be_selected_in_parent_and_fit_requested_count(library):
    first = create(library)
    unselected = next(row['sample_id'] for row in first['snapshot']['candidates']
                      if row['sample_id'] not in selected(first))
    with pytest.raises(ValueError, match='selected'):
        planner().regenerate_plan(first, seed=20, pins=[unselected])
    second = planner().regenerate_plan(first, seed=20, pins=selected(first)[:2])
    with pytest.raises(ValueError, match='pin'):
        planner().regenerate_plan(second, seed=30, count=1)


def test_planning_preserves_sources_database_and_parent_artifacts(library, tmp_path):
    root, db, _, _ = library
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    plan = create(library)
    output = tmp_path / 'plan-01'
    path = planner().write_plan(plan, output)
    loaded = planner().read_plan(path)
    assert loaded == plan
    assert (output / 'REVIEW.md').is_file()
    original = path.read_bytes()
    revised = planner().regenerate_plan(loaded, seed=99)
    planner().write_plan(revised, tmp_path / 'plan-02', parent_dir=output)
    assert path.read_bytes() == original
    assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert not list(output.glob('*.tsv'))
    with db._connect() as connection:
        assert connection.execute('select count(*) from reviews').fetchone()[0] == 0


def test_existing_nested_and_symlink_outputs_are_refused(library, tmp_path):
    plan = create(library)
    output = tmp_path / 'first'
    planner().write_plan(plan, output)
    with pytest.raises(ValueError, match='exist'):
        planner().write_plan(plan, output)
    with pytest.raises(ValueError, match='parent'):
        planner().write_plan(plan, output / 'nested', parent_dir=output)
    link = tmp_path / 'link'
    link.symlink_to(output, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink|exist'):
        planner().write_plan(plan, link)


def test_modified_plan_is_rejected_before_creating_any_output(library, tmp_path):
    plan = create(library)
    plan['selected'][0]['decision'] = 'favourite'
    with pytest.raises(ValueError):
        planner().write_plan(plan, tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()


def test_publication_in_library_state_respects_backup_lock(library):
    from librarytools.locking import library_lock, LibraryBusyError

    plan = create(library)
    root = library[0]
    output = root / '.eidetic' / 'runs' / 'collection-01'
    with library_lock(root, purpose='backup'):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(planner().write_plan, plan, output)
            with pytest.raises(LibraryBusyError):
                future.result()
    assert not output.exists()
    before = (root / '.eidetic/library.sqlite').read_bytes()
    saved = planner().write_plan(plan, output)
    assert planner().read_plan(saved)['plan_id'] == plan['plan_id']
    assert (output / 'REVIEW.md').is_file()
    assert (root / '.eidetic/library.sqlite').read_bytes() == before


def test_publication_refuses_foreign_or_unidentified_library_state(library, tmp_path):
    plan = create(library)
    other = tmp_path / 'other-library'
    other.mkdir()
    output = other / '.eidetic/runs/collection-01'
    with pytest.raises(ValueError, match='library identity'):
        planner().write_plan(plan, output)
    assert not (other / '.eidetic').exists()
    database = LibraryDatabase(other / '.eidetic/library.sqlite')
    database.bind_root(other)
    before = {p: p.read_bytes() for p in other.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='library identity'):
        planner().write_plan(plan, output)
    assert before == {p: p.read_bytes() for p in other.rglob('*') if p.is_file()}


def test_digest_rejects_boolean_changed_to_equal_integer(library):
    plan = create(library)
    plan['selected'][0]['pinned'] = 0
    with pytest.raises(ValueError, match='digest|content'):
        planner().validate_plan(plan)


def test_review_renders_brief_as_text_without_remote_markdown_images(library):
    root, db, _, _ = library
    path = root / 'PACKS' / 'tribal-pack' / 'perc-tribal-![remote](pixel).wav'
    path.write_bytes(b'a distinct source with a markdown filename')
    scan_library(root, db)
    brief = '![remote](https://example.invalid/pixel) and [link](https://example.invalid)'
    plan = create(library, brief=brief, count=13, freshness='allow')
    rendered = planner().review_markdown(plan)
    assert plan['policy']['brief'] == brief
    assert re.search(r'(?<!\\)\[[^\]]+\]\(', rendered) is None


def test_database_change_between_component_reads_aborts_before_publication(library, tmp_path, monkeypatch):
    from librarytools import collection_snapshot
    actual_load = collection_snapshot.load_index
    def change_between_reads(readonly_database):
        matches = actual_load(readonly_database)
        with library[1]._connect() as connection:
            connection.execute('update assets set size=size+1')
        return matches
    monkeypatch.setattr(collection_snapshot, 'load_index', change_between_reads)
    with pytest.raises(ValueError, match='changed during inspection'):
        plan = create(library)
        planner().write_plan(plan, tmp_path / 'mixed-snapshot')
    assert not (tmp_path / 'mixed-snapshot').exists()


@pytest.mark.parametrize('changes', [{'count': 0}, {'count': True}, {'seed': True},
                                    {'seed': -1}, {'device': 'unknown'}, {'freshness': 'default'}])
def test_invalid_controls_fail_without_library_mutation(library, changes):
    with pytest.raises(ValueError):
        create(library, **changes)


def test_initial_capture_requires_identity_and_complete_scan(tmp_path):
    root = tmp_path / 'samples'
    root.mkdir()
    db = LibraryDatabase(root / '.eidetic' / 'library.sqlite')
    options = dict(device='octatrack', count=5, freshness='allow', query=Query(),
                   brief='', seed=0, history_paths=[])
    with pytest.raises(ValueError, match='identity'):
        planner().create_plan(root, **options)
    db.bind_root(root)
    with pytest.raises(ValueError, match='scan'):
        planner().create_plan(root, **options)
