
                create table if not exists scans (
                    scan_id text primary key,
                    root text not null,
                    started_at text not null,
                    completed_at text,
                    status text not null check(status in ('incomplete','complete')),
                    file_count integer not null default 0
                );
                create table if not exists assets (
                    sample_id text primary key,
                    size integer not null,
                    extension text not null,
                    first_seen_at text not null
                );
                create table if not exists hash_cache (
                    device integer not null,
                    inode integer not null,
                    size integer not null,
                    mtime_ns integer not null,
                    sample_id text not null,
                    primary key(device, inode, size, mtime_ns)
                );
                create table if not exists locations (
                    path text primary key,
                    sample_id text not null references assets(sample_id),
                    zone text not null,
                    source_name text not null,
                    size integer not null,
                    mtime_ns integer not null,
                    scan_id text not null references scans(scan_id),
                    exists_now integer not null
                );
                create table if not exists asset_features (
                    sample_id text primary key references assets(sample_id),
                    payload_json text not null default '{}',
                    audio_error text not null default ''
                );
                create table if not exists annotations (
                    sample_id text primary key references assets(sample_id),
                    proposed_role text not null default '',
                    trusted_role text not null default '',
                    sample_type text not null default '',
                    bpm text not null default '',
                    musical_key text not null default ''
                );
                create table if not exists tags (
                    sample_id text not null references assets(sample_id),
                    tag_group text not null,
                    tag text not null,
                    primary key(sample_id, tag_group, tag)
                );
                create table if not exists reviews (
                    sample_id text not null references assets(sample_id),
                    packet_id text not null,
                    decision text not null,
                    true_role text not null default '',
                    descriptor text not null default '',
                    notes text not null default '',
                    reviewed_at text not null,
                    primary key(sample_id, packet_id)
                );
                create table if not exists promotions (
                    sample_id text not null references assets(sample_id),
                    curated_path text not null,
                    source_path text not null,
                    promoted_at text not null,
                    run_id text not null default '',
                    primary key(sample_id, curated_path)
                );
                create table if not exists origins (
                    sample_id text primary key references assets(sample_id),
                    origin text not null,
                    confidence text not null,
                    method text not null,
                    token text not null default ''
                );
                create table if not exists picks (
                    sample_id text not null references assets(sample_id),
                    kit_id text not null,
                    query text not null default '',
                    kept integer not null default 1,
                    recorded_at text not null,
                    primary key(sample_id, kit_id)
                );
                create table if not exists audio_embeddings (
                    sample_id text not null,
                    model_id text not null,
                    model_revision text not null,
                    excerpt_policy text not null,
                    dimensions integer not null check(dimensions > 0),
                    dtype text not null check(dtype = 'float16'),
                    embedding blob not null,
                    created_at text not null,
                    updated_at text not null,
                    primary key(sample_id, model_id, model_revision, excerpt_policy)
                );

PRAGMA user_version=3;
