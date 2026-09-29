# cr-s05e05-director

Temporal Flight Director Microservice for the CHRONOS-P1 Pocket Time Machine.

## Endpoints
- `GET /health` and `GET /`: Health and readiness check.
- `POST /run`: Triggers autonomous 3-hop temporal displacement trajectory and returns completion flag.
