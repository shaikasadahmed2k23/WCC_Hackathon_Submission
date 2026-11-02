# Vendor call with Razorpay

Date: 2026-10-30
Attendees: Priya Nair, Rahul Verma, Anita Sharma

Decision: we will go live with Razorpay for the fest registrations only after the webhook retry handling ships, because a missed callback would leave paid students unregistered.

Rahul Verma will test the Razorpay sandbox webhooks by 6 Nov.

The settlement account is the club's bank account, and the account holder must sign the KYC form.

Open question: does Razorpay support refunds for event fees collected through UPI?
