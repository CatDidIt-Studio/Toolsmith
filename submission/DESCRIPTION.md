# Toolsmith — submission text

**Track:** Fortified Enterprise Fleet

---

## What it does

An agent can only do what its tools and permissions allow, so the question
before handing over a job is not which model you are using — it is what the
job will actually reach. Nobody can see that list before they say yes.

Toolsmith answers it first. Given a task, it works out every step required,
which held tool performs each one, and the exact set of permissions those
steps will exercise. Then it asks once, before anything runs.

Where a step has no tool, it goes looking: searches MCP registries, opens the
candidate in an isolated sandbox to read what it actually offers, screens it,
and computes the minimum privilege that still does the job. If nothing can
close the gap, it says so and refuses to ask for approval at all — being told
a task is impossible now is worth more than discovering it halfway through
with permission already granted.

The unit of consent is the task, not the tool. Nobody wants to be interrupted
four times about servers they have never heard of.

## The problem it actually solves

A registry's tool description is, in practice, a self-authored resume. Reading
one to decide what to attach is closer to picking a restaurant from reviews
the restaurant wrote itself.

Existing MCP evaluation tools solve the opposite problem under opposite
constraints: offline, in batch, over hundreds of tasks, with minutes to spend
and nobody waiting. Screening in front of a person is online, in-loop, over a
handful of candidates, in seconds, cheap. Median verdict here is under a
second.

Permission names are never shown bare. Almost nobody knows GitHub's `repo`
scope reaches every private repository on the account, which is exactly why
over-broad access gets approved — the string looks modest and the consequence
is written nowhere the person clicking can see it. The card leads with the
consequence and puts the name second.

## How it is built

**Gemini 3.5 Flash** plans and executes. **Gemini 3.5 Flash-Lite** runs the
screening judges — the product claim is that screening is cheap enough to
happen while a human waits, so the judges run on the tier built for that.
**ADK 2.7** provides the agents and the tool plumbing. **Cloud Run** hosts the
sandbox, plus the two MCP servers the demo works against.

Two facts shape the architecture, and neither is task complexity.

The system reads text written by whoever published a tool while holding the
user's credentials. Those cannot share a context, so they do not: the screener
runs with no tools, no conversation history, no ability to plan or hand back
control, and a fixed output schema. If it is successfully injected, everything
it can return is a decision, a scope list and a set of finding codes. No prose
crosses the boundary, because prose is the attack.

And the material worth screening does not exist until you connect. The
registry publishes no tool definitions at all — descriptions and schemas are
only visible after opening a session with a server nobody has vetted. So first
contact happens in a disposable Cloud Run instance holding no credentials,
rather than in the agent's process. Anything that searches a registry and
attaches the winner is, structurally, attaching on metadata nobody verified.

Judgment and computation are separated throughout. Whether a description
changed since approval, whether the publisher signed it, whether a schema is
well-formed — these are computable, and computing them beats asking a model:
attacker text cannot argue with a diff.

Isolation is enforced rather than promised. A server cannot expose a tool
nobody approved, because the filter is applied at listing time. An executor
cannot exceed the approved plan, because out-of-plan calls are refused before
they reach a server — asking once only works if the answer binds.

## What we learned

**The public registry is mostly not there.** Of 40 entries listed as active
with an open endpoint, 15 answered. Nineteen refused the session, two did not
resolve, and one served a self-signed certificate — a listed, active server
whose identity cannot be established at all.

**Hosted MCP servers are moving to OAuth, and that is a real problem for this
idea.** They advertise only authorization code and refresh token grants, with
no machine-to-machine path, so a server will not say what it offers until it
has already been authorised. The material screening needs sits behind the very
decision screening exists to inform.

**Our own test corpus was the weakest thing we built.** The cases and the
screener prompt had the same author, so the bench only ever demonstrated
internal consistency. Pointing it at live servers found two false positives no
invented case could have: real descriptions say things like "use search first
to get the URL, then this tool", and we were blocking them as injected
instructions; and a perfectly ordinary schema that declares an optional
parameter as `anyOf` was being flagged as low quality, which would have
condemned a large share of the ecosystem.

**A bench that does not score the thing the system produces will certify a
broken system.** Ours scored decisions and finding codes and had no opinion
about the permission actually granted — the value the whole product computes.
It reported a case as correct while the screener handed over `public_repo`
where the answer was `issues:write`.

## Honest limits

The injection defence is not proven. We planted an instruction in a tool's
response mid-execution and the model declined it on its own, so the
enforcement layer never fired. The enforcement contract *is* proven — an
out-of-plan call is refused before reaching the server, and that test reports
inconclusive rather than pass when the model simply chooses not to overstep.

Two borderline screening cases move between warn and block across runs. Both
fail safe. It is instability rather than a decision, and it is reported rather
than tuned away.
