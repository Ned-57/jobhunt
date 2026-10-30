-- JobHunt schema for Supabase.
-- Run this in the SQL editor before setting JOBHUNT_STORAGE=supabase.
--
-- The app talks to Postgres through the service role, which bypasses RLS,
-- and scopes every query by user_id itself. The policies below exist so that
-- if you later move auth to Supabase Auth and use the anon key from the
-- browser, the data is already locked down per user.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- users
create table if not exists public.users (
  id            uuid primary key default gen_random_uuid(),
  email         text not null unique,
  password_hash text not null,
  created_at    timestamptz not null default now()
);

create index if not exists users_email_idx on public.users (lower(email));

-- ------------------------------------------------------------- profiles
-- One row per user. The whole profile is a JSON document because its shape
-- is driven by the questionnaire and changes more often than a schema
-- migration is worth.
create table if not exists public.profiles (
  user_id    uuid primary key references public.users (id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- --------------------------------------------------------- applications
create table if not exists public.applications (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.users (id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists applications_user_idx on public.applications (user_id, created_at);

-- Useful for filtering the tracker without pulling every row into Python.
create index if not exists applications_stage_idx
  on public.applications ((data ->> 'stage'));

-- ------------------------------------------------------ row level security
alter table public.users        enable row level security;
alter table public.profiles     enable row level security;
alter table public.applications enable row level security;

-- Scoped to Supabase Auth's auth.uid(). Harmless while the service role is
-- in use; correct the moment you switch the browser to the anon key.
drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own applications" on public.applications;
create policy "own applications" on public.applications
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own user row" on public.users;
create policy "own user row" on public.users
  for select using (auth.uid() = id);
