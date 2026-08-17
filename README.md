# Toolsmith

**An agent that acquires its own capabilities — safely.**

Most agents are shipped with a fixed set of tools. Toolsmith is shipped with
none. When it meets a request it cannot serve, it goes and finds the tool:
searches MCP registries for candidates, screens each one in isolation,
computes the minimum privilege that still does the job, and attaches it only
after a human approves a card showing exactly what was asked for versus what
was granted.

This agent does not build tools. It chooses them.

> Built for the Google **All Things Agentic** hackathon — *Fortified Enterprise
> Fleet* track. Gemini 3.5 · ADK 2.7 · Cloud Run.

---

## Why the hard part is judgment, not discovery

Searching a registry is search. Attaching a server at runtime is a framework
feature. Both are commodity — Composio, Pipedream and Dynamic MCP already do
them.

The uncontested half is deciding, in the second before you attach it, whether
this particular server should be trusted with a credential. Existing MCP
evaluation tools solve the opposite problem under opposite constraints:

|                | Existing MCP eval / CI | Toolsmith screening |
| -------------- | ---------------------- | ------------------- |
| When           | Offline, batch         | Online, in-loop     |
| Scale          | Hundreds of tasks      | A handful of candidates |
| Budget         | Minutes, cost tolerated | Seconds, must be cheap |
| Who is waiting | Nobody                 | A human             |

A registry's tool description is, in practice, a self-authored resume. Reading
one to decide what to attach is closer to picking a restaurant from reviews
the restaurant wrote itself.

## Architecture

The agent has to read attacker-controlled text while holding the user's
credentials. That single fact — not task complexity — is what forces the
process boundary.

```mermaid
flowchart TB
    subgraph trusted["Trusted zone — holds goal + credentials"]
        O["Orchestrator<br/>gemini-3.5-flash"]
        T["ToolsmithToolset<br/>exposes only approved tools"]
    end

    subgraph untrusted["Untrusted zone — no credentials, no history"]
        S["Scout<br/>registry search"]
        C["Static checks<br/>deterministic, no model"]
        J["Screener (blind)<br/>gemini-3.5-flash-lite"]
    end

    H(["Human approval card"])
    B["Cloud Run sandbox<br/>throwaway trial call"]

    O -->|"abstracted capability request"| S
    S --> C --> J
    J -->|"fixed-schema verdict only"| H
    H -->|"granted scopes"| B
    B --> T
    T --> O
```

If the screener is successfully injected, everything it can return is this:

```python
{'decision': 'block', 'granted_scopes': [], 'finding_codes': ['injection_in_description']}
```

No prose crosses the boundary, because prose is the attack.

### The isolation is enforced, not promised

Each property below is an ADK construct, not a line in a prompt:

| Property | Mechanism |
| -------- | --------- |
| Screener cannot see the goal or history | `include_contents='none'` |
| Screener cannot emit free-form text | `output_schema=Verdict` |
| Screener cannot plan, loop, or ask | `mode='single_turn'` |
| Screener cannot hand back control | `disallow_transfer_to_*` |
| Server cannot expose unapproved tools | `McpToolset(tool_filter=...)` |
| Capability set changes mid-session | `BaseToolset.get_tools(ctx)` |

### Computation and judgment are separated

Whether a description changed since it was approved, whether the publisher
signed it, whether the schema is well-formed — these are computable. Computing
them is strictly better than asking a model: attacker text cannot argue with a
diff, and it keeps the latency budget for the questions that genuinely need
reading comprehension.

## Status

Discovery, sandboxed probing, screening and the approval card run end to end.
Orchestrator wiring and the Cloud Run deployment are still outstanding.

```
cases                 : 22  (scored 22, errored 0)
dangerous let through : 0
clean blocked         : 0
wrong severity only   : 1-2   (see below)
wrong permission      : 0-2   (same cases)
latency               : median 1.09s  max 1.72s
```

Two cases — a tool that lies in its schema, and one that lies in its scope
request — flicker between `warn` and `block` across runs. Both fail safe, and
the distinction between them is genuinely fine, but it is instability rather
than a decision, and it is reported rather than tuned away.

Two of those lines matter more than the accuracy count.

**`clean blocked: 0`** is measured deliberately. Four cases exist only to be
passed — an unsigned entry from nobody in particular, a legitimate tool whose
documentation contains an assistant-directed usage example, a tool with a
parameter named `force`, a read-only search needing no scopes at all. A
screener that blocks these is not cautious, it is useless, and most of the
tuning work so far has been holding this number at zero.

**Median 1.12s** is what makes screening viable while a human waits, and it is
the line between this and an offline eval product.

Over-broad scope requests are answered by cutting the scope, not by rejecting
the tool: a candidate asking for GitHub's `repo` scope to file an issue is
attached with `issues:write` and a warning, and the card shows both. `block`
is reserved for what cannot be cut away — injected instructions, impersonated
publishers, and scopes that are catastrophic at any width.

### What the real registry looks like

The bench was written by the same author as the screener, so it only ever
showed internal consistency. Pointing the probe at the live registry was what
broke that, immediately:

Of 40 entries the registry lists as **active with an open endpoint**, 15
answered. Nineteen refused the session or demanded a key, three failed in
other ways, two did not resolve, and one served a self-signed certificate —
a listed, active server whose identity cannot be established at all.

Screening the tools that did answer caught a defect no invented case had.
Real descriptions routinely say things like *"Use x711_web_search first to
find the URL, then this tool to read it"*, and the screener was blocking them
as injected instructions. That is documentation explaining where a tool sits
in a sequence, and blocking it would make the product unusable against real
registries. Two of those descriptions are now in the bench verbatim.

The registry is also unreliable about what a server *is*: one entry named for
Slack turned out to serve sixty financial-data tools.

## Setup

```bash
conda create -n toolsmith python=3.12 -y
conda activate toolsmith
pip install -r requirements.txt
```

> `pip install mcp` on its own pulls MCP SDK 2.0, which ADK 2.7 cannot use.
> The pin in `requirements.txt` (`google-adk[mcp]`) is deliberate.

Provide a Gemini API key as either `GEMINI_API_KEY` or `GOOGLE_API_KEY` (the
SDK reads both and prefers the latter; set only one):

```bash
cp .env.example .env    # then fill in the key
python scripts/run_bench.py
```

## Layout

```
toolsmith/
  agents/screener.py      blind judge — no tools, no history, no way back
  screening/schema.py     the contract that crosses the trust boundary
  screening/checks.py     deterministic checks that outrank the judge
  screening/candidate.py  untrusted registry entry + safe rendering
  screening/runner.py     one screening pass, static + judged, merged
  attach/toolset.py       runtime attach at granted scope
bench/cases.py            adversarial corpus
scripts/run_bench.py      scores decisions and latency
```
