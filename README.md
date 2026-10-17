# ToleranceOracle

A reusable GenLayer Intelligent Contract primitive for reading a numeric fact from a web page, with consensus based on numeric tolerance and evidence verification.

- Deployed contract (Studio): `<PASTE_CONTRACT_ADDRESS>`
- Explorer: `<PASTE_EXPLORER_LINK>`

## Problem

LLM-extracted numbers are rarely identical across validators. Rounding, formatting, and pages that change between fetches make `strict_eq` fail often. A loose "are these similar?" LLM comparison is too weak to trust with money. This contract replaces both with a precise custom equivalence rule.

## How consensus works

1. The leader fetches the page and extracts a number plus a verbatim evidence quote.
2. Each validator independently fetches the page and extracts its own number.
3. A validator approves only if both conditions hold:
   - the leader's value is within `tolerance_bps` of the validator's own value;
   - the leader's evidence quote appears in the validator's own copy of the page.
4. Regardless of consensus, the value must fall inside the feed's `[min_value, max_value]` bounds, or the update is rejected.

Values are non-negative fixed-point integers with 6 decimals (`1.5` is stored as `1500000`), so no floats are stored.

## Methods

| Method | Type | Description |
|---|---|---|
| `create_feed(feed_id, url, question, unit, tolerance_bps, min_value, max_value)` | write | Registers a feed. Bounds are scaled by 1e6. `tolerance_bps` is 1 to 5000. |
| `update(feed_id)` | write | Runs a consensus round and stores the new value and evidence. Callable by anyone. |
| `get_latest(feed_id)` | view | Returns round, value, unit, evidence quote, source, and tolerance. |
| `get_config(feed_id)` | view | Returns the feed configuration. |

## Failure modes handled

| Case | Result |
|---|---|
| Page does not contain an answer | Round fails |
| Quote not found in page | Round fails |
| Value is not a plain non-negative number | Round fails |
| Validators disagree beyond tolerance | No consensus |
| Value outside sanity bounds | Update rejected |
| Leader errors and validators succeed | Validators disapprove |

## Example

```
create_feed(
  "example_feed",
  "https://example.com/page-with-the-number",
  "Current value of X in percent",
  "percent",
  100,
  1000000,
  100000000
)
update("example_feed")
get_latest("example_feed")
```

This creates a feed with 1% tolerance (100 bps) and bounds of 1.0 to 100.0.

## Use as a building block

Other contracts can use a feed as a threshold input, for example in escrows, conditional payouts, or markets that settle on a published number.

## Deploy

1. Open GenLayer Studio and paste `contracts/tolerance_oracle.py`.
2. Deploy with no constructor arguments.
3. Call `create_feed`, then `update`, then `get_latest`.

## Test results

Add your own results here, for example:

- Normal case: value extracted and stored, round increments.
- Missing number: round fails.
- Value outside bounds: rejected.
- Tight tolerance: consensus fails when validators differ.
