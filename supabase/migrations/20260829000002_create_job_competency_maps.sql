-- Structured competency maps produced by the deterministic JD parsing pipeline.
-- One row per parsed job description; the raw JD lives in job_descriptions.

create table if not exists public.job_competency_maps (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null unique references public.job_descriptions(id) on delete cascade,
  schema_version text not null default '1.0',
  model text,
  payload jsonb not null,               -- fully validated competency-map object
  validation_status text not null default 'ok',  -- ok | repaired | failed
  validation_notes jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists job_competency_maps_set_updated_at on public.job_competency_maps;
create trigger job_competency_maps_set_updated_at
  before update on public.job_competency_maps
  for each row
  execute function public.set_updated_at();

grant select on public.job_competency_maps to anon, authenticated;