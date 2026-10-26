# Alex Rivera

Backend & AI Engineer · Lisbon, Portugal

## Summary

Backend engineer with 6 years of experience building payment and logistics systems in Python and Go, and the last two years shipping LLM features to production.

## Experience

### Senior Backend Engineer · Parcelly (logistics) | Mar 2023 – Present

Delivery tracking platform, 2M shipments a day

- Built a delivery-time prediction service in Python (FastAPI, scikit-learn) that cut late-delivery complaints by 18%.
- Added an LLM support assistant with RAG over 4,000 help-center articles, answering 40% of tickets without an agent.
- Moved batch jobs from cron on EC2 to Kubernetes CronJobs with Helm, and set up Grafana alerts for failed runs.
- Mentored three junior engineers and ran the weekly architecture review.

### Backend Engineer · Paylane (fintech) | Jan 2020 – Feb 2023

- Designed an idempotent payments API in Go with PostgreSQL, handling 300 requests per second at peak.
- Built fraud rules on Kafka streams that flagged suspicious refunds within two seconds.
- Wrote integration tests against real Postgres in CI with GitHub Actions, raising coverage from 40% to 85%.

## Projects

- **Recipe Scout:** a LangGraph agent that plans weekly meals from a fridge photo, with Gemini vision and a human approval step. Python, LangGraph, React.

## Technical Skills

- **Languages:** Python, Go, SQL, TypeScript
- **AI / LLM:** RAG, LangGraph, LangChain, OpenAI, Gemini, pgvector, prompt evaluation
- **Infrastructure:** AWS (EC2, S3, RDS), Kubernetes, Helm, Docker, Terraform, GitHub Actions, Grafana
