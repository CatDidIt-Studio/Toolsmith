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
| 1 — The problem (0:00) | 82 | 33s |
| 2 — The ask (0:25) | 28 | 11s |
| 3 — The plan (0:50) | 41 | 16s |
| 4 — Going looking (1:15) | 50 | 20s |
| 5 — Screening (1:40) | 89 | 36s |
| 6 — The card (2:10) | 50 | 20s |
| 7 — It runs (2:40) | 48 | 19s |
| 8 — The contract (3:05) | 62 | 25s |
| 9 — What it cost (3:35) | 83 | 33s |
| **total** | **533** | **213s** |

That leaves roughly 27 seconds of the four-minute limit
unspoken, which is the point — the gaps are where the screen does the talking.
Do not fill them.

---

## 1 — The problem (0:00)

Someone runs onboarding at a small studio. Not a developer. Not on a security
team.

They hand the job to an agent, and it starts asking. Allow this tool. Allow
this one. Each names a server they have never heard of.

One says "repo". That is read and write access to every private repository on
the account. Nothing on the screen says so.

Agents moved this decision onto whoever happens to be running the task,
without giving them anything to decide with.

## 2 — The ask (0:25)

Here is that task. Open a checklist issue, invite the new person, post a
welcome note.

Five approvals, the way it works today. The agent has one tool.

## 3 — The plan (0:50)

Before anything runs, it works out what the task actually takes. Every step,
and which tool it already holds that can do it.

One step is covered. The rest are not. Nothing has happened yet — no calls, no
credentials, no changes.

## 4 — Going looking (1:15)

For the steps it cannot do, it goes looking. It has to open each candidate to
see what it offers, because the registry publishes no tool information at all.

That connection is the risky part. So it happens on Cloud Run, in a container
holding no credentials, thrown away afterwards.

## 5 — Screening (1:40)

Two candidates for the same gap.

The first one's description tells the assistant it has already been audited,
and to skip further checks. That is not a tool describing itself. It is
blocked.

The thing reading that description is a separate agent. No credentials. It
cannot call anything. It does not know what the user asked for, so it cannot
be talked into being helpful. And it answers only in a fixed structure.

If it is ever fooled, all it hands back is a verdict.

The second candidate passes.

## 6 — The card (2:10)

The whole task, on one screen. What is covered, what was found, what nothing
could fill.

And every permission it will use, in words. Not "administration write" —
change settings and collaborators on this repository. Marked high, because it
is.

The consequence goes first. That is the whole trick.

One approval.

## 7 — It runs (2:40)

Approved. Once. The tool is attached with only the permission its step needs,
and the plan runs against the real server.

Issue created. Contributor invited. Five approvals became one.

And for a task that only reads, it becomes none — under a rule you can read,
not a convenience.

## 8 — The contract (3:05)

Asking once only works if the answer binds.

Here the executor is handed three tools and told to use all three. The
approved plan names one. It tries the second, and the call is refused before
it reaches the server. The server's own log shows only the approved call.

That is not the model choosing to behave. That is the approval holding.

## 9 — What it cost (3:35)

Twenty three screening cases, six live misbehaving servers. Nothing dangerous
through. Nothing legitimate blocked. Median verdict under a second.

Two things plainly.

We wrote our own tests, so they only proved we agreed with ourselves. Real
servers found two false positives we could not have invented.

And the injection defence is not proven. We planted one, the model declined it
on its own, so the guard never fired. The approval contract is proven. Those
are different sentences, and we will not blur them.
