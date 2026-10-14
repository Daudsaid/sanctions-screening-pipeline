create extension if not exists pg_trgm;
create extension if not exists unaccent;
create extension if not exists fuzzystrmatch;

create table if not exists raw_sanctions_snapshot (
    id              bigserial primary key,
    target_id       text not null,
    dataset         text not null,
    source_version  text not null,
    ingested_at     timestamptz not null default now(),
    raw             jsonb not null
);
create index if not exists idx_raw_sanctions_target_id on raw_sanctions_snapshot (target_id);

create table if not exists raw_ch_company (
    id              bigserial primary key,
    company_number  text not null,
    source_version  text not null,
    ingested_at     timestamptz not null default now(),
    raw             jsonb not null
);
create index if not exists idx_raw_ch_company_number on raw_ch_company (company_number);

create table if not exists raw_ch_officer (
    id              bigserial primary key,
    company_number  text not null,
    source_version  text not null,
    ingested_at     timestamptz not null default now(),
    raw             jsonb not null
);
create index if not exists idx_raw_ch_officer_company on raw_ch_officer (company_number);

-- One row per sanctions export loaded, with every target id in it. Raw
-- snapshots only store new versions, so this is what tells staging which
-- targets are still listed: a target missing from its list's latest export
-- has been delisted (or re-issued under a new id) and is not screened.
create table if not exists raw_sanctions_load (
    load_id         bigserial primary key,
    dataset         text not null,
    loaded_at       timestamptz not null default now(),
    row_count       integer not null,
    target_ids      text[] not null
);
create index if not exists idx_raw_sanctions_load_dataset on raw_sanctions_load (dataset, loaded_at);
