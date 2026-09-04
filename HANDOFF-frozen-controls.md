# Handoff: a demo's controls stop responding, and a rebuild undoes the payload work

Written 2026-09-04 by the corestone session, which found both while deploying
the granite weathering exercise. Neither is a corestone problem: the first is
in `artesian.live.animator` and affects every demo built on it, and the second
is a footgun in the build command that will keep firing.

Everything below was measured, not reasoned. The measurement harness and raw
data are under the scratchpad path named at the end; the summary numbers are
here so you do not have to rerun anything to decide.

---

## 1. The controls freeze, and it is event-loop starvation

### The symptom

Reported by Andy: *"Sometimes during a run the controls become unresponsive."*
The "sometimes" is the diagnostic clue -- it depends on whether any animation
frame lands under the callback period.

### The cause, in one line of Panel

`panel/io/callbacks.py`, `PeriodicCallback._async_repeat`, in
`panel-1.9.4-py3-none-any.whl` -- read from the installed package, not quoted
from memory:

```python
while True:
    start = time.monotonic()
    await func()                                   # NOT a suspension point
    timeout = (self.period/1000.) - (time.monotonic()-start)
    if timeout > 0:
        await asyncio.sleep(timeout)               # the ONLY yield
```

`await func()` awaits a coroutine directly, which does not yield to the event
loop, and `_periodic_callback` contains no await when the step function is
synchronous -- which is what `animator` passes it:

```python
ticker = pn.state.add_periodic_callback(lambda *a: step(), period=period, ...)
```

So the **only** yield is that conditional sleep. When a frame overruns the
period, `timeout <= 0`, the sleep is skipped, and the loop spins with zero
returns to the JS event loop. In `pyodide-worker` mode the worker's
`onmessage` -- which applies the widget patch and posts `{type:'idle'}` back --
is a JS task and can never run. **The controls are not slow. They are
disconnected**, for as long as no frame comes in under the period.

Replicated in plain CPython with the same loop shape, counting how often a
competing task got scheduled over 60 frames at a 33 ms period:

```
frame  30.0 ms -> competitor ran  30498 times
frame  32.0 ms -> competitor ran   9826 times
frame  34.0 ms -> competitor ran      0 times      <- cliff at the period
frame  70.0 ms -> competitor ran      0 times
```

### What it looks like in a browser

Headless Chrome, corestone demo, latency from setting a Bokeh model to the app
visibly responding:

| cell | T | achieved fps | median frame | running slider | running button |
|---|---|---|---|---|---|
| 5 cm | 12 C | 24.8 | 33.3 ms | 64 ms | 63 ms |
| 2.5 cm | 30 C | 13.4 | 66.7 | 188 | 269 |
| **2 cm** | **30 C** | **9.8** | **83.3** | **no response in 30 s** | **no response in 30 s** |

The 2 cm / 30 C failure is total and reproducible, 4/4 probes, and Pause never
took effect either. What predicts it is not the mean frame cost but the
**longest run of consecutive over-budget frames**: 16 at 5 cm/12 C, 130 at
2 cm/30 C. Frame cost is bimodal -- cheap frames plus periodic expensive ones
where the model re-solves its flow field -- so responsiveness survives as long
as *some* frame squeaks under the period. Hence "sometimes".

Ticks are **dropped, not queued** -- structurally impossible to queue, since
`_async_repeat` is a sequential loop. Confirmed: the clock stops the instant a
Pause event lands, with no backlog draining. Widget events *do* queue, but on
the main thread: the bridge showed `{busy: true, queued: 2}` with the first
event posted to the worker and never acknowledged.

### The fix, two lines, in artesian

Make the step a coroutine so the yield happens inside the tick. Panel's
`_periodic_callback` does `await cb` when the callback returns an awaitable:

```python
def animator(step, period=DEFAULT_PERIOD, ...):
    async def _step(*a):
        step()
        await asyncio.sleep(0)          # hand the event loop back, every frame
    ticker = pn.state.add_periodic_callback(_step, period=period, start=False)
```

Measured at 2 cm / 30 C, three paired A/B reps interleaved so machine load is
shared between arms:

```
rep0 base  median frame  97.5 ms  latency [None, None, None]   pause never took effect
rep0 fix   median frame  85.5 ms  latency [511, 567, 240] ms   pause immediate
rep1 base  median frame  83.4 ms  latency [None, None, None]   pause never took effect
rep1 fix   median frame  66.5 ms  latency [319, 350, 350] ms   pause immediate
rep2 base  median frame  99.7 ms  latency [None, None, None]   pause never took effect
rep2 fix   median frame 126.1 ms  latency [634, 463, 300] ms   pause immediate
```

3/3: dead against responsive. The patched arm stayed responsive through runs
of **192 consecutive frames each over 33 ms** -- the condition that kills the
baseline. Throughput is unaffected; the medians overlap and are unordered.

**Rejected, with reasons.** Raising the period only moves the cliff --
starvation returns whenever frames exceed the new period, and it slows every
setting including the ones that were fine. A re-entrancy guard does nothing,
because ticks never re-enter; the loop is already sequential.

**Residual, not a bug.** Even fixed, latency at the worst setting is 0.3-0.9 s,
which is one frame plus the model rebuild. That is intrinsic cost, not lost
events.

### Worth reporting upstream

The real fix is one line in Panel -- `await asyncio.sleep(timeout if timeout >
0 else 0)` -- so the loop yields even when a callback overran. The artesian
change is a local workaround for a library that starves its own event loop
under a slow callback, which is a reasonable thing for Panel to want to fix.

---

## 2. A plain build silently re-inflates the stripped wheels

`--strip-vendored` took a demo's self-hosted payload from 36.9 MB to 11.5 MB
(commits `a2f871d`, `aa13856`, `92c2f0c`). But the flag is off by default and
nothing notices when it is missing:

```
plain `artesian build`  ->  panel-1.9.4-py3-none-any.whl   30.3 MB
currently deployed          panel-1.9.4-py3-none-any.whl    9.4 MB
```

**Same filename, same output directory, 21 MB difference, no warning.** Any
downstream rebuild without the flag overwrites a stripped wheel with a fat one
and the next reader pays for it. This nearly happened on GeomorphOnline: the
corestone demo was rebuilt six times on 2026-09-04 with a plain build command,
and the payload survived only because a later session rebuilt everything with
the flag.

Being off by default is right -- a stripped wheel is not what `pip install`
gives under that filename, and the existing docstring says so. The problem is
that it is silent.

**Suggestion, not a decision.** When a build is about to overwrite an existing
wheel with a *larger* file of the same name, say so:

```
note: panel-1.9.4-py3-none-any.whl in this directory is 9.4 MB; this build
      writes 30.3 MB. Re-run with --strip-vendored to keep it stripped.
```

That turns a silent regression into a line of output, without changing any
default. The existing payload report already computes both numbers.

---

## Where the evidence lives

Harness, raw JSON and logs:
`/tmp/claude-1000/-home-awickert-models/4065e39e-397e-47e4-ba95-a58467696988/scratchpad/meas/`
(`sweep2.json`, `fd_base.json`, `fd_fix.json`, `ab.json`, `loopdemo.py`), with
patched builds in `../_spin_fix` and `../_spin_fix2`. Scratchpaths do not
survive a reboot; the numbers above are the durable record.

One caveat on absolute values: these were measured in headless Chrome with
software GL on a loaded workstation, and the frame costs are several times what
the corestone demo's own docstring predicts natively. **Treat the pattern as
the finding, not the milliseconds.** The A/B comparison is immune to this, since
both arms ran interleaved on the same machine.
