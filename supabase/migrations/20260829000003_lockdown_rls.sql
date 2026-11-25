-- Security lockdown: both JD tables are private data.
--
-- Enable RLS on every table and remove all anon/authenticated privileges granted
-- in earlier migrations. No auth layer exists in this project, so there are no
-- per-role policies. With RLS enabled and zero policies, the anon and
-- authenticated roles are denied completely; only service_role (used by
-- jd_pipeline.py, Studio, and the management API) and the owner bypass RLS.

alter table public.job_descriptions enable row level security;
alter table public.job_competency_maps enable row level security;

revoke all on public.job_descriptions from anon, authenticated;
revoke all on public.job_competency_maps from anon, authenticated;