# Core team meeting

Date: 2026-09-12
Attendees: Priya Nair, Rahul Verma, Meera Iyer, Karthik Reddy

Decision: we will use PostgreSQL instead of MongoDB for all event data because registrations need transactional consistency.

Decision: the mobile wrapper will stay on Capacitor for this semester because rewriting it in Flutter would take at least six weeks.

Priya Nair will test the database rollback procedure before the October release.

Open question: who will hold the Google Play Console account after Priya graduates?

Risk: the payment webhook has no retry handling, so a missed callback leaves the registration pending.

Karthik Reddy owns the poster design workflow.
