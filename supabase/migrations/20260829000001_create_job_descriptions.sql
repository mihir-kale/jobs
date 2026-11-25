-- Job descriptions store. Raw text saved as-is; metadata extracted by an LLM later.

create table if not exists public.job_descriptions (
  id uuid primary key default gen_random_uuid(),
  title text,
  company text,
  url text,
  jd_text text not null,
  source text default 'manual',        -- manual paste, url, file, llm, etc.
  status text default 'new',           -- new | ats_ready | applied | withdrew | archived
  metadata jsonb default '{}'::jsonb,  -- LLM-extracted fields (skills, deadlines, salary, ...) later
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Fill updated_at on any update.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists job_descriptions_set_updated_at on public.job_descriptions;
create trigger job_descriptions_set_updated_at
  before update on public.job_descriptions
  for each row
  execute function public.set_updated_at();

-- Local dev convenience: let anon/authenticated roles read and insert so the
-- supabase-py / supabase-js clients work without auth friction. RLS is off for now.
grant select, insert, update on public.job_descriptions to anon, authenticated;