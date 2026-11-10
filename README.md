# Wanderly Travel

Travel storefront client code, deployed by the Cloud-Agnostic Application
Control Plane from this repository:

- `site/` — static frontend (destination search, trip pages, booking, My trips)
- `api/` — custom Lambda API (Aurora PostgreSQL catalog + DynamoDB bookings)

Merges to `main` auto-deploy (control-plane releasePolicy: on-commit);
each deployment is versioned by commit SHA.
