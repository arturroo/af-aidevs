# cr-s05e05-cockpit

Cockpit Actuator Microservice for the CHRONOS-P1 Pocket Time Machine.

## Endpoints
- `GET /health`: Health and readiness check.
- `POST /controls`: Sets physical directional switches (`PTA`, `PTB`), shield potentiometer (`PWR`), and power mode (`standby` / `active`).
- `GET /telemetry`: Queries live DOM state from `$AIDEVS_TIMETRAVEL_PREVIEW_URL`.
- `POST /activate-jump`: Monitors `internalMode` rotation and activates the glowing orb upon reaching the designated phase.
