---
slug: email-deliverability
title: Email Going to Spam — SPF/DKIM/DMARC
triggers: email going to spam, going to spam, landing in spam, in spam folder, emails in spam, spf, dkim, dmarc, email not delivered, mail not sending, emails bounce, email deliverability, mail goes to junk, going to junk
os: any
priority: 5
---
GOAL: Diagnose WHY mail is rejected or junked — authentication (SPF/DKIM/DMARC),
reputation, or delivery mechanics — and fix in the right order.

DIAGNOSTIC ORDER (read-only first):
1. Establish HOW the site sends mail: direct from this server (postfix/sendmail, PHP
   mail()) or via SMTP relay/API (SendGrid, SES, Mailgun…)? `systemctl status postfix`
   + the app's mail settings. The fix differs completely.
2. Check the three DNS records for the sending domain:
   - SPF: `dig +short TXT <domain>` → one v=spf1 record naming every legit sender
     (the server's IP and/or the relay's include:). TWO spf records = broken.
   - DKIM: `dig +short TXT <selector>._domainkey.<domain>` (selector from the mailer:
     often 'default', 'mail', or the relay's docs).
   - DMARC: `dig +short TXT _dmarc.<domain>` → start with p=none (monitor), move to
     quarantine/reject only after SPF+DKIM pass consistently.
3. Send a real test to a Gmail address and read "Show original" — it grades
   SPF/DKIM/DMARC pass/fail directly. That's the ground truth.
4. Server-send problems: `tail -30 /var/log/mail.log` (or maillog) — look for
   "blocked", "rate limit", or bounces naming a blocklist.
5. Reputation: many VPS IP ranges are pre-flagged. If logs show blocklist bounces,
   check the IP on a DNSBL (Spamhaus etc.) — and be honest: delisting a cheap VPS IP
   is often futile.
6. PTR record: reverse DNS must resolve to a hostname that resolves back — set at the
   VPS provider panel, not in the zone file.

PITFALLS:
- Never create a second SPF record — merge into ONE (multiple = automatic fail).
- SPF has a 10-DNS-lookup limit — too many include: chains silently break it.
- Don't jump DMARC to p=reject on day one; legitimate mail dies. p=none + rua reports
  first, tighten in 1–2 weeks.
- DNS changes take up to the TTL to apply — tell the user to wait before re-testing.
- THE HONEST DEFAULT: for a business on a generic VPS, sending via a reputable relay
  (SES/Mailgun/Postmark, most have free tiers) beats fighting IP reputation. Recommend
  it when the goal is "emails must arrive" rather than "run my own mail server".

VERIFY: a fresh test mail to Gmail shows SPF=pass, DKIM=pass, DMARC=pass in "Show
original" and lands in the inbox, not spam.

ROLLBACK: DNS records are additive/replaceable — keep the old record values noted in
the chat before changing them.
