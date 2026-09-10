# NeedsAfrica API

Backend for NeedsAfrica, a nonprofit platform where visitors browse charitable
projects, donate to them, subscribe for updates, and sign up to volunteer.

Built with Django 5.2 and [django-ninja](https://django-ninja.dev/). Auth is JWT
via `djangorestframework-simplejwt`, wrapped in a Ninja `HttpBearer` so all
routers are authenticated by default.

The frontend that consumes this API lives in
[needsafricafe](https://github.com/Jaysins/needsafricafe).

## API surface

All routes are mounted under `/api/`, with interactive docs at `/api/docs`.

| Router | Prefix | What it covers |
| --- | --- | --- |
| `api/auth_api.py` | `/api/auth/` | Register and login |
| `api/project_api.py` | `/api/project/` | Project CRUD, photo upload and deletion, per-project report download, aggregate stats |
| `api/donation_api.py` | `/api/donation/` | Donations, Paystack and PayPal webhooks, PayPal payment execution |
| `api/volunteer_api.py` | `/api/volunteer/` | Volunteer signups |
| `api/subscription_api.py` | `/api/subscription/` | Newsletter subscriptions |

Django admin is at `/admin/`.

## Data model

`api/models.py` defines `User`, `Project`, `ProjectPhoto`, `Donation`,
`Volunteer`, `Subscription` and `ExchangeRate`. The exchange rate table lets
donations be recorded in a donor's currency and reported in a single base
currency.

## Third-party services

- **Paystack** — card and bank donations in NGN, confirmed by webhook
- **PayPal** — international donations, confirmed by webhook
- **Cloudinary** — storage for project photos, via `django-cloudinary-storage`
- **SendGrid** — transactional email

## Running locally

Requires Python 3.11+ and a PostgreSQL database.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then fill in the values

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The API is then at `http://localhost:8000/api/` and the docs at
`http://localhost:8000/api/docs`.

## Configuration

Every setting is read from the environment — see `.env.example` for the full
list with placeholder values. `DATABASE_URL` and the Cloudinary, Paystack,
PayPal and SendGrid credentials have no defaults and must be set.

## Deployment

`build.sh` is the release command: it installs dependencies, runs
`collectstatic`, and applies migrations. The app is served by `gunicorn`.
