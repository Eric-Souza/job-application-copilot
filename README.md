# Job Application Copilot

A LangGraph agent that tailors your resume to a job posting. Paste a posting, and the agent extracts the requirements, matches them against your experience with RAG, and drafts tailored resume bullets. You review the drafts before anything is finalized. Every run is saved in Postgres, so you can close the tab and resume later.

> **Status:** the experience index and the core LangGraph agent (milestones 1 and 2) work from the CLI: parse a posting, retrieve evidence, match requirements, draft grounded bullets. Human review with a Postgres checkpointer is next.

## How it works

```
job posting
  │
  ▼
parse_posting ──► retrieve_experience ──► match_requirements ──► draft_bullets ──► human_review ──► finalize
(structured        (pgvector RAG over      (coverage + gaps       (tailored            (interrupt:       (tailored resume
 requirements)      your resume/projects)   per requirement)       bullets + sources)   approve / edit /   section + summary)
                                                                        ▲               request changes)
                                                                        └──── revise ◄─────────┘
```

1. **parse_posting:** an LLM call with structured output (Pydantic) turns the posting into must-have and nice-to-have requirements, seniority, and stack.
2. **retrieve_experience:** for each requirement, hybrid search over your resume, project write-ups, and articles stored in pgvector.
3. **match_requirements:** scores coverage per requirement and lists gaps, with the evidence it found.
4. **draft_bullets:** writes tailored bullets that cite which experience each one came from. It only uses retrieved evidence, so it doesn't invent experience.
5. **human_review:** the graph pauses with a LangGraph `interrupt`. You approve, edit, or ask for changes, and changes loop back to drafting.
6. **finalize:** produces the tailored resume section and a short summary you can paste into an application.

## Features

- [x] LangGraph `StateGraph` with typed state, conditional edges, and retry policies for a busy free tier
- [x] Structured outputs with Pydantic models for requirements, matches, and bullets
- [x] Grounding checks in code: every bullet must cite one role's evidence; invented numbers, mixed roles, and tools that role never used are flagged
- [x] RAG over your experience: resume-aware chunking, Gemini embeddings, pgvector, hybrid search (vector + Postgres full-text, merged with Reciprocal Rank Fusion)
- [ ] Human-in-the-loop review with `interrupt` and resume
- [ ] Postgres checkpointer (`langgraph-checkpoint-postgres`), so runs survive restarts and can be resumed by thread ID
- [ ] Token and step streaming to the React UI over SSE
- [ ] Tool calling: the agent can fetch more context when a requirement has weak evidence
- [ ] Langfuse tracing with per-run cost and latency
- [ ] Optional: load experience through the [profile MCP server](https://github.com/Eric-Souza/profile-mcp-server) instead of local files

## Stack

| Area | Choice |
|------|--------|
| Agent | LangGraph, LangChain |
| API | Python, FastAPI, SSE |
| LLM | Google Gemini (free tier), with Groq or local Ollama as alternatives |
| Embeddings | Gemini embeddings |
| Database | Postgres + pgvector (Docker locally, Neon free tier hosted) |
| Agent state | LangGraph Postgres checkpointer |
| Frontend | React, TypeScript, Vite, MUI |
| Observability | Langfuse (Hobby free tier) |
| Tests | pytest, Vitest |

## Project structure

```
job-application-copilot/
  apps/
    api/                    # FastAPI + LangGraph
      app/
        graph/
          state.py          # typed graph state
          builder.py        # StateGraph wiring, retry policies, checkpointer
          prompts.py        # system and user prompts per node
          grounding.py      # deterministic checks on drafted bullets
          nodes/            # parse_posting, retrieve_experience, match, draft, review, finalize
        routers/            # runs, review decisions, SSE stream, experience ingestion
        services/
          chunking.py       # resume Markdown -> one chunk per bullet, tagged with its role
          ingest.py         # embed and index files, skip unchanged ones, prune removed ones
          retrieval/        # vector, keyword, and hybrid (RRF) search
          llm.py            # Gemini chat model (with a lite fallback) and embeddings
        cli.py              # python -m app.cli ingest | search | tailor
        schemas.py          # Pydantic models (requirements, matches, bullets)
      tests/
    web/                    # React UI: posting input, live run view, review screen
  data/resume/              # your resume and project write-ups (gitignored)
  data/samples/             # a fictional sample resume and job posting
  docs/                     # design notes, screenshots
  docker-compose.yml        # Postgres 16 + pgvector
  .env.example
```

## Getting started

```bash
cp .env.example .env        # add GEMINI_API_KEY
docker compose up -d        # Postgres + pgvector on localhost:5435

cd apps/api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Put your resume in `data/resume/` as Markdown (see [`data/resume/README.md`](data/resume/README.md) for the format, and [`data/samples/sample-resume.md`](data/samples/sample-resume.md) for an example). Then index it and try a search:

```bash
python -m app.cli ingest                     # one batched embedding request per changed file
python -m app.cli search "Kafka microservices" -k 3
```

```
1. [Technical Skills]
   Architecture: System design, microservices, event-driven systems (Kafka, Pub/Sub), multi-tenant SaaS
   rrf=0.033 vector=0.669 keyword=0.400
2. [Experience] Full Stack Engineer · Zro Bank | Jul 2020 – Jun 2022 > Multi-currency digital bank (fintech)
   Scaled the core banking app's backend by splitting it into NestJS microservices that communicate over Apache Kafka, ...
```

Each chunk is one resume bullet, and its role heading is embedded and indexed with it, so a requirement like "healthcare experience" finds bullets whose only mention of healthcare is the job title above them.

Tests run against a separate `copilot_test` database and never call Gemini:

```bash
pytest
```

Tailor your resume to a posting (a sample one is included):

```bash
python -m app.cli tailor ../../data/samples/postings/senior-ai-engineer.md --out tailored.md
```

```
   7.9s  parse_posting
   9.7s  retrieve_experience
  37.8s  match_requirements
  52.7s  draft_bullets
  52.7s  finalize
```

The output has a summary, bullets grouped by the role they came from, a requirement coverage table (strong, partial, missing, with the evidence ids), and the must-haves with no evidence. Any bullet that fails a grounding check carries a `Check:` line saying what to verify.

The API and the React UI land in later milestones.

## Free to run

- **Gemini API (AI Studio):** free tier for chat and embeddings.
- **Postgres + pgvector:** local Docker, or Neon's free tier.
- **Langfuse Hobby:** free tracing.
- **Ollama:** fully local, if you'd rather not send your resume to an API.
