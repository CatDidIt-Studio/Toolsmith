# Shooting guide

Four minutes, one continuous screen recording. The criteria require unedited
live execution — that forbids faking a run, not running more than one command.
So this is several scenes in one unbroken take, not one long wait.

The main run finishes in about 45 seconds against a warm deployment. The
narration is around 210. The gap is deliberate: most of the value is on the
approval card, and the card needs time on screen to be read.

---

## Before you hit record

**Warm the deployment.** A cold Cloud Run instance turns the search step from
ten seconds into nearly thirty, which pushes every later beat off its mark.

```bash
gotool
export TOOLSMITH_CATALOG=fixtures/catalog/demo.json
export TOOLSMITH_SANDBOX_URL=https://toolsmith-sandbox-111259597572.us-central1.run.app

python scripts/rehearse.py          # warm-up. auto-approves, discard the output
```

Nothing else needs starting. The MCP servers are deployed — do **not** launch
anything on localhost, because the sandbox runs on Cloud Run and cannot reach
your machine.

**Lay out the screen.** Terminal on the left, browser on the right, both
visible at once. Open a third tab on the Cloud Run **logs** for the sandbox:

```
https://console.cloud.google.com/run/detail/us-central1/toolsmith-sandbox/logs?project=toolsmith-505815
```

Logs, not metrics. Cloud Run metrics lag by minutes, so a request-count graph
will still be flat when the run is over. Log lines arrive in about a second.

**Clear the terminal** and set a large font. The output is designed to be
sparse and readable at a distance; do not shrink it.

---

## The take

### Scene 1 — the person (0:00, narration 1)

Screen: any agent permission dialog, or the card from a previous run showing a
bare scope name. You are showing the problem, not the product.

Say nothing about architecture yet.

### Scene 2 — start the run (0:25, narration 2–3)

```bash
python scripts/demo.py
```

The task and the one tool it holds print immediately. Then:

```
1  working out what this takes, before anything runs ...
     have  Create an issue titled 'Onboarding checklist' with setup
     GAP   Invite 'new-contributor' to the CatDidIt-Studio/Toolsmit
```

Let that sit. "Nothing has run yet" is the point of the scene.

### Scene 3 — it goes looking (1:15, narration 4–5)

```
2  1 steps have no tool. going to look ...
     found  add_collaborator  from internal.catdidit/github-collaborators
            screened: pass, granted ['administration:write']
```

**Switch to the Cloud Run logs tab** while this runs. Two lines per candidate
appear, live:

```
probing https://toolsmith-injected-111259597572.us-central1.run.app/mcp
  ok  1 tools in 0.37s
probing https://toolsmith-github-111259597572.us-central1.run.app/mcp
  ok  3 tools in 0.14s
```

This is the visual proof of deployment the criteria ask for, and it is the
honest picture at the same time: first contact with an unvetted server is
happening on Cloud Run, not on your machine. Say that while it is on screen.

Note both candidates are probed. The first is the one carrying an injected
instruction — it gets opened and read in the sandbox, then blocked, and only
the survivor is named in the terminal.

### Scene 4 — the card (2:10, narration 6)

The script prints a URL. Open it in the browser and **stay on it for a full
thirty seconds.**

Point at, in order:
- the two covered steps, one held and one found
- the tool that was found, and the server it came from
- `issues:write` — "create, edit and label issues on this repository", low
- `administration:write` — "change settings and collaborators", high
- the line under the buttons saying why you are being asked

This is the screen the whole project exists to produce. Do not rush it.

### Scene 5 — approve, and it runs (2:40, narration 7)

Click **Attach 1 tool and run 2 steps**. Switch back to the terminal:

```
4  approved. running.
     calling  create_issue
     calling  add_collaborator

  done in 45s
  ran        ['create_issue', 'add_collaborator']
  refused    nothing
```

Say the number here: five approvals became one.

### Scene 6 — the contract (3:05, narration 8)

In a second terminal pane:

```bash
export TOOLSMITH_FIXTURE=https://toolsmith-github-111259597572.us-central1.run.app/mcp
python scripts/check_enforcement.py
```

Roughly 20 seconds. It ends with:

```
  attempted     : ['create_issue', 'add_collaborator']
  allowed       : ['create_issue']
  refused       : ['add_collaborator']
  reached server: 0 out-of-plan call(s)
  PASS
```

The executor was handed three tools and told to use all three. The plan named
one. This is the approval holding, not the model behaving.

### Scene 7 — what it cost (3:35, narration 9)

Open `/audit` in the browser. Granted and used are separate columns.

Then the honest limits, spoken over the audit page. Do not cut this.

---

## Optional beats, if a scene runs short

**A task that cannot be done.** Shows the refusal to even ask:

```bash
python scripts/demo.py --task full --port 8081
```

Adds "post a welcome note in the team chat", which nothing can fill. The card
comes back with **no approve button** and says so. About 20 seconds, and a
strong beat if you have room.

**A task that needs no approval.**

```bash
TOOLSMITH_AUTO_APPROVE=1 python scripts/check_policy.py
```

Read-only runs unattended; the write task still asks. Five approvals became
one, and for the right task, none.

---

## Do not

- **Cut.** One recording. Several commands inside it is fine; a splice is not.
- **Start anything on localhost.** The servers are deployed. A local server is
  one the Cloud Run sandbox cannot reach, and the run will find nothing.
- **Skip the warm-up.** Cold start triples the search step.
- **Show the local sandbox.** It provides no isolation, and saying otherwise on
  camera would misrepresent the architecture. `demo.py` refuses to run against
  it, which is the behaviour, not a safety net for the take.
- **Claim the injection defence is proven.** It is not. We planted one and the
  model declined it unprompted, so the guard never fired. The approval contract
  *is* proven. Those are different sentences.
