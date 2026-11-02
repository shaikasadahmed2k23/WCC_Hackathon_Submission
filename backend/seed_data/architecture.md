# Architecture notes

Date: 2026-09-02

CampusConnect has three services: the API, the worker and the notification service. The worker uses Celery with Redis as the broker to send confirmation emails and generate QR passes.

We decided to store uploaded event posters in an S3 bucket because the EC2 disk filled up twice in August.

The payment webhook endpoint /payments/webhook must stay reachable, otherwise registrations stay in the pending state.
