# web/

Framtida webapp-implementation (Flet / FastAPI / annat).

Kan återanvända `core/` och `services/` direkt eftersom de är rena Python-moduler
utan Qt-beroenden.

## Planerat dataflöde

```
web/routes.py  →  services/job_service.py  →  core/*
```
