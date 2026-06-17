# Zenoti Unofficial API

Unofficial Python integrations for Zenoti.

## Integrations

- `zenoti_list_guests.py` - `list_guests`.
- `zenoti_get_guest_profile.py` - `get_guest_profile`.
- `zenoti_list_appointments.py` - `list_appointments`.
- `zenoti_list_employees.py` - `list_employees`.

## Usage

Each file exposes a `run(input, context)` entrypoint. The runtime is expected to provide:

- `input`: integration-specific request fields.
- `context["headers"]`: authenticated request headers when required.
- `context["base_url"]`: the platform base URL when overriding the default.

Install dependencies:

```bash
pip install -r requirements.txt
```

## Info

This unofficial API is built by [Integuru](https://integuru.com).

For custom requests or hosted authentication, contact richard@integuru.com or [schedule time with us](https://calendly.com/d/cqb8-d9x-nbf/integuru).

See the [complete list of APIs by Integuru](https://github.com/Integuru-AI/APIs-by-Integuru).
