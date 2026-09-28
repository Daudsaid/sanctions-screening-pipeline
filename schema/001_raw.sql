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
