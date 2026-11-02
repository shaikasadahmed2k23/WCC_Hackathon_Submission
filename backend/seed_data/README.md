# CampusConnect

CampusConnect is the events and club-membership app used by the GPCET technical clubs. Students register for events, pay fees and receive QR entry passes.

Date: 2026-08-20

## Stack

The backend is a FastAPI service backed by PostgreSQL 15. Redis is used for OTP rate limiting. The web client is React and the mobile wrapper is built with Capacitor.

## Deployment

The API runs in Docker on an AWS EC2 instance in the Mumbai (ap-south-1) region to keep latency low for campus users. Deployments run automatically from the main branch through GitHub Actions.

Priya Nair owns the backend and the deployment pipeline. Rahul Verma maintains the React web client.

## Known issues

The QR pass generator fails when two students register in the same second. The fix is in branch fix/qr-race and still needs review.

Do not run database migration 0007 on production without taking a backup first.
