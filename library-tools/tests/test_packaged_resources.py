from pathlib import Path

from librarytools import profiles, tagging


def test_bundled_profiles_and_vocabulary_match_canonical_sources():
    resource_dir = Path(profiles.__file__).parent / 'resources'
    for source in profiles.PROFILE_ROOT.rglob('*.toml'):
        assert (resource_dir / 'profiles' / source.relative_to(profiles.PROFILE_ROOT)).read_bytes() == source.read_bytes()
    assert (resource_dir / 'vocabulary.toml').read_bytes() == tagging.DEFAULT_VOCABULARY.read_bytes()


def test_resources_can_resolve_without_a_source_checkout():
    resource_dir = Path(profiles.__file__).parent / 'resources'
    profile = profiles.resolve_profile(profile_root=resource_dir / 'profiles')
    assert profile.devices
    assert tagging.load_vocabulary(resource_dir / 'vocabulary.toml')
