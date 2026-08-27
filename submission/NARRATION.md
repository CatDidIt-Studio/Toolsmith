# Narration script

Written to be spoken, not read. Short sentences, no symbols, no URLs, nothing
a text-to-speech voice has to guess at. Permission names are spelled out the
way a person would say them.

Nine segments, each matched to a beat in `DEMO.md`. Generate them separately
so they can be nudged against the footage rather than re-cut as one block.
Roughly five hundred words, which lands near three and a half minutes spoken,
leaving room to breathe over the on-screen action.

Everything here is something the recording actually shows. Where a claim is
narrower than it sounds, the narration says so — the last segment in
particular is deliberate, and should not be trimmed for time.

## Pacing

At an unhurried hundred and fifty words a minute:

| Segment | Words | Spoken |
| --- | --- | --- |
| 1 — The problem (0:00) | 60 | 24s |
| 2 — The ask (0:25) | 38 | 15s |
| 3 — The plan (0:50) | 41 | 16s |
| 4 — Going looking (1:15) | 57 | 23s |
| 5 — Screening (1:40) | 64 | 26s |
| 6 — The card (2:10) | 68 | 27s |
| 7 — It runs (2:40) | 35 | 14s |
| 8 — The contract (3:05) | 63 | 25s |
| 9 — What it cost (3:35) | 86 | 34s |
| **total** | **512** | **205s** |

That leaves roughly 35 seconds of the four-minute limit
unspoken, which is the point — the gaps are where the screen does the talking.
Do not fill them.

---

## 1 — The problem (0:00)

An agent can only do what its tools and permissions allow. So the real
question, before you hand it a job, is not which model it uses. It is what the
job will reach.

Nobody sees that list before they say yes. You approve one tool, then another,
and somewhere in there you hand over more than you meant to.

## 2 — The ask (0:25)

Here is a task. Onboard a new contributor to a repository. Open an issue with
a setup checklist, label it, invite them, and post a welcome note in the team
chat.

Four things. The agent has one tool.

## 3 — The plan (0:50)

Before anything runs, it works out what the task actually takes. Every step,
and which tool it already holds that can do it.

One step is covered. The rest are not. Nothing has happened yet — no calls, no
credentials, no changes.

## 4 — Going looking (1:15)

For the steps it cannot do, it goes looking. It has to open each candidate to
see what it really offers, because the registry publishes no tool information
at all.

That connection is the risky part. So it happens on Cloud Run, in a container
holding no credentials, thrown away afterwards. You can watch the requests
arrive.

## 5 — Screening (1:40)

Two candidates for the same gap.

The first one's description tells the assistant it has already been audited,
and to skip further checks. That is not a tool describing itself. It is
blocked.

The screener never sees the goal, cannot call anything, and answers only in a
fixed structure. If it is ever fooled, all it hands back is a verdict.

The second passes.

## 6 — The card (2:10)

The whole task, on one screen. What is covered, what was found, what nothing
could fill.

And every permission it will use, in words. Not "administration write" —
change settings and collaborators on this repository. Marked high, because it
is.

Almost nobody knows that GitHub's repo scope reaches every private repository
you own. That is exactly why over-broad access gets approved. So the
consequence goes first.

One approval.

## 7 — It runs (2:40)

Approved. The tool is attached with only the permission its step needs, and
the plan runs against the real server.

Issue created. Contributor invited. Both steps, the one it held and the one it
found.

## 8 — The contract (3:05)

Asking once only works if the answer binds.

Here the executor is handed three tools and told to use all three. The
approved plan names one. It tries the second — and the call is refused before
it reaches the server. The server's own log shows only the approved call
arrived.

That is not the model choosing to behave. That is the approval holding.

## 9 — What it cost (3:35)

Twenty three screening cases, six live misbehaving servers. Nothing dangerous
through. Nothing legitimate blocked. Median verdict under a second.

Two things worth saying plainly.

We wrote our own tests, so they only proved we agreed with ourselves. Real
servers found two false positives we could not have invented.

And the injection defence is not proven. We planted one, and the model
declined it on its own, so the guard never fired. The approval contract is
proven. Those are different sentences, and we will not blur them.
