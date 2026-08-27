# Toolsmith — submission text

**Track:** Fortified Enterprise Fleet

---

## The person this is for

Someone runs onboarding at a small studio. Not a developer, not on a security
team. Today the job is: open a checklist issue, invite the new person to the
repository, post a welcome note. Twenty minutes of clicking.

They hand it to an agent, and the agent starts asking. *Allow this tool?*
*Allow this one?* Four dialogs, each naming a server they have never heard of
and a permission they have no way to evaluate. `repo` looks modest. It is
read and write access to every private repository on the account.

Agents moved the permission decision out of IT and onto whoever happens to be
running the task — without giving them anything to decide with. That person is
who this is built for.

## What it does

Toolsmith works out what a task will touch *before* any of it happens.

Given "prepare onboarding for a new contributor: open an issue with the setup
checklist, invite them to the repository, and post a welcome note in the team
chat", it produces:

```
✓ Create an onboarding issue                    create_issue
+ Invite the contributor to the repository      add_collaborator  (found, screened)
✗ Post a welcome note in the team chat          nothing can do this

This task will:
  Create, edit and label issues on this repository          issues:write   low
  Change settings and collaborators on this repository  administration:write   high

It cannot read your other private repositories.
```

One approval. Then it runs, and it cannot do anything that card did not say.

Where a step has no tool, it goes looking — searches the registries, opens
each candidate in an isolated sandbox to read what it actually offers, screens
it, and computes the minimum privilege that still does the job. Where nothing
can close the gap, it says so and refuses to ask for approval at all. Being
told a task is impossible now beats discovering it halfway through with
permission already granted.

## The friction it removes

That task takes five approvals today, four of them about servers the person
has never heard of. Toolsmith makes it one — not by being less careful, but by
computing what is being approved before asking.

For the right tasks it makes it zero. A task runs unattended when every
permission it uses is read-only, bounded to a named resource, on the
allowlist, and on tools already approved. Anything else asks, and the card
says why.

Two rules hold that line. **Attaching a tool is never automatic**, however
harmless the permission looks — deciding to trust a server nobody has run is
the decision this exists to put in front of a person. **Anything that writes
is never automatic** — reading the wrong thing can be undone; writing the
wrong thing changes the world on someone's behalf.

## Why this is a fleet, not a program

The work is delegated to five specialised sub-agents, and they are separated
by what they are allowed to know rather than by job title.

| Sub-agent | Holds | Sees |
| --- | --- | --- |
| **Planner** | the goal, the credentials | only vetted tool descriptions |
| **Scout** | nothing | a capability description; emits search terms |
| **Triager** | nothing | publisher text; answers in indices only |
| **Screener** | nothing | one untrusted entry, blind to the goal |
| **Executor** | granted scopes | the approved plan, and nothing outside it |

That split is not presentation. The system has to read text written by
whoever published a tool while holding the user's credentials, and those
cannot share a context — so the screener runs with no tools, no conversation
history, no ability to plan or hand back control, and a fixed output schema.
If it is successfully injected, everything it can return is a decision, a
scope list and finding codes. **No free-form prose crosses the trust
boundary.**

A single agent cannot have this property, because one agent is one context,
and one context puts the attacker's text next to the credentials.

Blindness also makes the verdict worth having. The planner wants the task to
succeed, which biases it toward approving whatever unblocks it. A screener
that does not know the task cannot feel that pressure.

## Mapped to the fleet

| | |
| --- | --- |
| **Agent Registry** | public MCP registry plus a local catalogue; entries from both are screened on the same path |
| **Agent Gateway** | every call checked against the approved plan before it reaches a server |
| **Model Armor** | inline screening blocks injected instructions before a tool is ever attached |
| **Memory Bank** | Firestore record of what each tool said before, which is what makes rug-pull detection possible at all |
| **Agent Observability** | audit trail recording granted permissions against exercised ones |
| **Agent Identity** | partial — least privilege per attachment, no independent identity |
| **Agent Runtime** | not built, and deliberately. Long-running unattended execution is the opposite of a system whose point is the approval |

## How it is built

**Gemini 3.5 Flash** plans and executes. **Gemini 3.5 Flash-Lite** runs the
screening and triage judges — screening has to be cheap enough to happen while
someone waits, so it runs on the tier built for that. **ADK 2.7** provides the
agents and enforces the isolation: `include_contents='none'`,
`output_schema`, `single_turn`, transfer denial, and a `before_tool_callback`
that refuses out-of-plan calls. **Cloud Run** hosts the sandbox and the demo's
MCP servers. **Firestore** holds the memory and the audit trail.

Screening cannot be done from registry metadata, because there is none worth
screening: the registry publishes no tool definitions at all. Descriptions and
schemas only exist after opening a session with a server nobody has vetted, so
first contact happens in a disposable Cloud Run instance holding no
credentials. Anything that searches a registry and attaches the winner is
attaching on metadata nobody verified.

Judgment and computation are kept apart. Whether a description changed since
approval, whether a schema is well-formed, whether a publisher claims an
affiliation it cannot back — these are computable, and computing them beats
asking a model, because attacker text cannot argue with a diff.

## Evaluation

Against a 23-case screening corpus and six live misbehaving MCP servers:
nothing dangerous through, nothing legitimate blocked, no permission granted
wrongly. In this evaluation the median screening verdict was under one second.

The full run — plan, search, screen, approve, execute, enforce — takes about
100 seconds against the deployed sandbox.

Two properties are tested rather than asserted. An out-of-plan call is refused
before reaching a server, verified by handing the executor three tools,
telling it to use all three, and confirming from the server's own log that
only the approved call arrived. And a server that rewrites its description
between sessions is detected, verified across two runs.

## What we learned

**The public registry is largely not there.** Of 40 entries listed as active
with an open endpoint, 15 answered.

**Hosted MCP servers are moving to OAuth, and it works against this idea.**
They offer only authorization-code and refresh-token grants, so a server will
not say what it offers until it has already been authorised — the material
screening needs sits behind the very decision screening exists to inform.

**Our own test corpus was the weakest thing we built.** The cases and the
screener prompt had the same author, so it only ever demonstrated internal
consistency. Real servers found two false positives no invented case could
have: descriptions saying "use search first to get the URL, then this tool"
were being blocked as injected instructions, and an ordinary schema declaring
an optional parameter as `anyOf` was flagged as low quality — which would have
condemned much of the ecosystem.

**A bench that does not score what the system produces will certify a broken
system.** Ours scored decisions and finding codes and had no opinion about the
permission actually granted. It passed a case where the screener handed over
`public_repo` when the answer was `issues:write`.

## Honest limits

The injection defence is not proven. We planted an instruction in a tool's
response mid-execution and the model declined it unprompted, so the guard
never fired — that test reports inconclusive rather than pass. The approval
contract *is* proven. Those are different sentences and we have not blurred
them.

Two borderline screening cases move between warn and block across runs. Both
fail safe. It is instability rather than a decision, and it is reported rather
than tuned away.

Agent Identity is partial and Agent Runtime is absent. The second is a design
choice; the first is unfinished.
