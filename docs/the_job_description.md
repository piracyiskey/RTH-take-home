# The job

Thanks for taking the time to do this. Before you start, a bit about the client, what to build and how we score it.

## The client and the problem

Robusttechhouse Properties manages three buildings, in Singapore, Sydney and Jakarta. Each building (we call it a site) has its own timezone, opening hours and public holidays. Tenants raise requests in a helpdesk, things like "room too warm" or "lift stuck on level 4". Each request has a priority, and as staff work on it the helpdesk records events: status changes, who was assigned, notes, deadline changes.

The director asked us this:

> "For each site, how fast do our teams respond, and how often does work finish late? I want to pick any date range in the last six months and see it."

That's what you're building: a small web app that answers that question from the helpdesk's data. You get your own copy of the helpdesk with made-up data (see "Your practice API" on this page). The kit explains how to read from it and exactly what your app should return.

## What to build

Work through these in order. We score each level separately.

1. **The report.** For a date range, one line per request: who responded, how fast, whether that was within target, and whether the work finished late. Plus a summary per responder. Show it on a simple page and return the same data from an endpoint. You're done when any date range gives the right answers.
2. **Make it fast.** The full six months is about 12,000 requests. Once your app says it's ready, six months should come back in under 10 seconds and a single month in under 5.
3. **Keep it live.** The helpdesk keeps changing while your app runs. A change should show up in your report within a minute.
4. **Let them browse.** A list of the report's lines with filters, sorting and paging, on a page and from an endpoint. Everything should still work while the data is changing underneath.

The exact endpoints and response shapes are in `docs/contract.md` in the kit.

## The rules

Everything is in the site's local time. The seven rules (which requests count, who responded, what counts as late, and so on) are in `docs/rules.md` in the kit. There are no hidden ones.

## How we score it

We look at whether it works, your `DECISIONS.md`, your code and your commits, and whether a client could follow your notes and your short video (about 3 minutes).

## A few practical things

- Cap it at three hours. Node, Rails or Python, your choice; there's a starter for each in the kit. Any front end. Add a database if you want one.
- You may use AI tools. Whatever you submit, you should understand every line of it and be able to explain it in the interview. If you used them, say what for in `DECISIONS.md`.
- If the data or the API surprises you, that's part of the test. Handle it and write it down.
- The client may send you a message on this page while you work, like a real project. Check back.
- Commit as you go, at least five times. We read the history.
- Submit even if it's unfinished, and say in `DECISIONS.md` what you'd do next.

Good luck, and enjoy it.