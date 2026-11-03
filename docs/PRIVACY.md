# Privacy

What happens to what visitors send. The site's footer says it in one paragraph; this is the
long form.

## The public record

Every verdict is published in the public record, word for word, with the law that decided it.
The form says so, and won't send a case until the visitor ticks a box confirming they
understand; the API refuses a case for the record without that consent. The form has two
parts, labelled as such: the grievance, which goes to the court and the record, and the
accused's names, the visitor's own name and a photo, which stay on the device (see Decrees).
The grievance is written without names, and the form refuses one that contains a name typed
in the private part. Three more safeguards apply:

- A case that contains an email address, a phone number or a link is judged but not
  published, and the visitor is told why.
- Anyone can report a case. A case with enough reports (three by default) is hidden until the
  site's owner reviews it, then restored or deleted.
- Whoever files a case gets a private removal link. It deletes the case for good, at any
  time. Only a hash of the key is stored.

Declined cases have no verdict and are never published; they're kept only in the private history (below). The record stores what was written,
the outrage level, the themes, the ruling with its law, and when it was filed. It stores no
names beyond what visitors write, no IP addresses, and no trace IDs.

## Everything else visitors write

A grievance goes to the API on Microsoft Azure, which sends it to Groq to be judged, or, if Groq can't answer, to the next provider in `providers.toml`, such as Cloudflare Workers AI. Groq doesn't
retain inference data by default, and with Zero Data Retention turned on in its Data Controls
(Step 16), it doesn't log it even temporarily. Gemini is supported as a fallback for local
development only: on Google's free tier, prompts may be used to improve Google's products, so
production leaves `GEMINI_API_KEY` unset.

The API keeps no cache and no access log. Its rate limiter counts visitors by a keyed
fingerprint of their address, never the address itself, and replaces the key every day. Its
own log lines, timings and errors but never a visitor's words, are kept by Azure for 31 days.

With tracing on, Langfuse records the shape of each request: which steps ran, how long they
took, which model answered, how many tokens it used, and any error. Decorated calls capture no
arguments or results, and before anything is sent, every attribute that could hold a prompt,
an answer or metadata is deleted. A thumbs-up or thumbs-down is stored as a number.

## Names, the visitor's details and decrees

The accused's names, the visitor's own name and a photo go in the form's private part. The
browser uses them to show the verdict with those names on the visitor's own screen, and draws
them into the decree image. They are never sent: not to the API, not to the public record, not
to analytics, not anywhere. The court and the record only ever see "the Plaintiff" and "the
Accused". The photo is kept
only as a small copy in the page's memory, until it's removed or the page is closed, and the
exported image carries none of the original photo's metadata, such as where it was taken.

## The court's history

Every grievance filed through the form is also kept privately, word for word (up to 5,000
characters), with what became of it: a verdict, contempt, declined, too long to judge, or not
judged because the court was down. That includes cases that are never published, such as
those containing contact details, and grievances over 600 characters, which are kept but never
sent to an AI. The form says so before anything is filed. Only the site's owner can read the
history, with `tribunal history`; the API never serves it. It holds no names from the private
part of the form, no photos, no addresses and no fingerprints. A visitor's removal link
deletes their entry too, and the owner can delete old entries with `tribunal history --prune`.
Requests stopped by rate limits, health checks and load tests are not kept.

## The ledger

The System page reads a ledger of counts: cases a day, by kind, the law each one cited, which
AI provider answered, the tokens used, and how many requests were refused before reaching the
AI. It holds numbers only: no grievance, name, address or fingerprint.

## On the visitor's device

The site remembers one thing in the browser's local storage: the skin the visitor chose. It is
never sent anywhere.

## Visit statistics

With a PostHog key in `frontend/config.js`, the site counts visits anonymously: page views,
clicks on buttons and links, and these events. None of them contains what anyone typed.

- `case_submitted`: the outrage level, the themes, the jurisdiction, and the grievance's length
- `verdict_shown`: the cited law's ID, theme, jurisdiction and tier, and whether it's quoted
- `contempt_found`: the cited law, as for `verdict_shown`, when a petition that isn't a
  grievance is held in contempt
- `case_declined`: nothing else
- `court_unavailable`: the HTTP status, or 0 when the API didn't answer
- `famous_case_shown`: why the archive was shown, and the law its verdict cites
- `feedback_sent`: a thumbs-up (1) or a thumbs-down (-1)
- `catalog_unavailable`: the HTTP status
- `system_opened`: nothing else
- `skin_changed`: the skin chosen
- `library_opened`: whether the laws or the verdicts were opened
- `law_opened`: the ID of a law whose verdicts were opened
- `case_reported`: nothing else
- `case_removed`: nothing else
- `decree_exported`: the design, how many names (never the names), whether it has a photo
  (never the photo), and download or share

No cookies are used, nobody is identified, browsers that send Do Not Track aren't counted, and
sessions are never recorded. With "Discard client IP data" turned on in PostHog's project
settings (Step 16), addresses aren't stored either. Analytics are always off on localhost.

## The daily check

`scripts/uptime.py` sends one made-up grievance a day to confirm the court works, marked to
stay out of the public record. It counts toward the daily budget, like any other case.