Put your resume and project write-ups here (Markdown, TXT, or PDF). Everything in this folder except this README is gitignored.

Markdown works best, because the indexer follows its structure and makes one chunk per bullet:

```markdown
# Your Name                                  <- ignored

## Experience                                <- section
### Senior Engineer · Acme | 2022 – 2024     <- context, stored with every bullet below
Healthcare data platform                     <- a line under a role adds to its context
- Built clinical dashboards with React.      <- one chunk
- Cut report times by 60% with Redis.        <- one chunk

#### Nested headings (clients, projects) add to the context too

## Summary
A paragraph under a heading with no bullets becomes its own chunk.
```

PDFs and plain text are split into fixed-size chunks instead, so they lose the role context. See `data/samples/sample-resume.md` for a full example.

Index the folder with `python -m app.cli ingest` from `apps/api`. Unchanged files are skipped, and files you delete here are removed from the index.
