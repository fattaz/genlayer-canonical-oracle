# CanonicalOracle

A reusable GenLayer Intelligent Contract primitive for reading a numeric fact from a web page and committing **one canonical value** through consensus.

- Deployed contract (Studio): `0xB70E1C5f26F0252d539d08114FA308A52083eFfc`
- Explorer: `https://explorer-studio.genlayer.com/address/0xB70E1C5f26F0252d539d08114FA308A52083eFfc`

## Problem

LLM-extracted numbers differ slightly between validators (rounding, formatting, a page that updates between fetches). If consensus accepts a *range* of leader values and then stores the leader's raw value, two different values can both pass validation and push a downstream threshold in different directions.

CanonicalOracle removes that ambiguity. Every value that validators can accept is the same value, so there is exactly one material outcome per round.

## How consensus works

Each feed has a `step`, the grid size that all stored values must sit on, in the same 6-decimal fixed-point units as the value.

1. The leader fetches the page and extracts a number plus a verbatim evidence quote.
2. The number is rounded to the nearest multiple of `step` (half up). This is the **canonical value**.
3. Each validator independently fetches the page and computes its own canonical value the same way.
4. A validator approves only if all of these hold:
   - the leader's value is an exact multiple of `step`;
   - the leader's value is inside the feed's `[min_value, max_value]` bounds;
   - the leader's canonical value is **exactly equal** to the validator's own canonical value;
   - the leader's evidence quote appears in the validator's own copy of the page.
5. The stored value is the agreed canonical value. The evidence quote is informational and has no effect on the number.

### Design trade-off: fail closed

Two readings that are very close can still round to different grid points if they straddle a rounding boundary (for example 8848.49 and 8848.50 with a step of 1). In that case validators disagree and the round fails. No value is stored and the round can be retried. The contract never stores an ambiguous value, it just declines to answer.

Choose `step` so the true value is not near a rounding boundary, and so downstream thresholds fall on grid points. With a step of `1000000` (1 unit), a threshold of 8,000 behaves identically for every value in the round's accepted set.

Values are non-negative fixed-point integers with 6 decimals (`1.5` is stored as `1500000`).

## Methods

| Method | Type | Description |
|---|---|---|
| `create_feed(feed_id, url, question, unit, step, min_value, max_value)` | write | Registers a feed. `url` must start with `https://`. `step` is at least 1. `min_value` and `max_value` are scaled by 1,000,000. |
| `update(feed_id)` | write | Runs a consensus round and stores the canonical value and evidence. Callable by anyone. |
| `get_latest(feed_id)` | view | Returns round, value, unit, evidence quote, source, and step. |
| `is_at_least(feed_id, threshold)` | view | Returns whether the latest canonical value is at least `threshold` (scaled). Errors if the feed has no value yet. |
| `get_config(feed_id)` | view | Returns the feed configuration. |

### Scaling reference

| Real value | Pass this number |
|---|---|
| 0.01 | `10000` |
| 1 | `1000000` |
| 1,000 | `1000000000` |
| 10,000 | `10000000000` |

## Deploy

1. Open [GenLayer Studio](https://studio.genlayer.com) and paste `contracts/canonical_oracle.py`.
2. Deploy with no constructor arguments.

## Testing guide

Run these in order in Studio's "Run and Debug" tab. A transaction can show `ACCEPTED` as its consensus status while its result is `ERROR`, so always check the **Result** field.

### Test 1: create a feed with a fine step

Method: `create_feed`

| Argument | Value |
|---|---|
| `feed_id` | `everest_height` |
| `url` | `https://en.wikipedia.org/wiki/Mount_Everest` |
| `question` | `What is the elevation of Mount Everest above sea level in metres?` |
| `unit` | `metres` |
| `step` | `10000` |
| `min_value` | `1000000000` |
| `max_value` | `10000000000` |

Expected: result not `ERROR`.

### Test 2: run a consensus round

Method: `update` with `feed_id` = `everest_height`

Expected: result not `ERROR`. This takes longer than other calls because each validator fetches the page and runs the LLM.

### Test 3: read the result

Method: `get_latest` with `feed_id` = `everest_height`

Expected (the evidence wording can differ slightly, but it always contains `8,848.86`):

```json
{
  "round": 1,
  "value_scaled": 8848860000,
  "value": "8848.860000",
  "unit": "metres",
  "evidence": "... 8,848.86 m (29,031.7 ft) ...",
  "source": "https://en.wikipedia.org/wiki/Mount_Everest",
  "step": 10000
}
```

### Test 4: use the value in a threshold check

Method: `is_at_least`

| `feed_id` | `threshold` | Expected |
|---|---|---|
| `everest_height` | `8000000000` | `true` |
| `everest_height` | `9000000000` | `false` |

### Test 5: see canonicalization with a coarse step

1. `create_feed` with `feed_id` = `everest_coarse`, the same `url`, `question`, `unit`, `min_value`, and `max_value` as Test 1, and `step` = `1000000`.
2. `update` with `feed_id` = `everest_coarse`.
3. `get_latest` with `feed_id` = `everest_coarse`.

Expected: `value_scaled` is `8849000000` and `value` is `"8849.000000"`. The page value 8848.86 was rounded to the nearest whole unit, so every validator stores the same canonical number.

### Failure cases

Each of these should end with result `ERROR` and no stored value.

| # | Method and arguments | Expected error |
|---|---|---|
| 6 | `create_feed` with an empty `url`, or one starting with `http://` | `url must be https` |
| 7 | `create_feed` with `feed_id` = `everest_height` again | `feed already exists` |
| 8 | `create_feed` with `step` = `0` | `step must be at least 1` |
| 9 | `create_feed` with `min_value` = `5000`, `max_value` = `1000` | `invalid bounds` |
| 10 | `create_feed` with `step` = `100`, `min_value` = `1`, `max_value` = `10` | `step larger than bounds range` |
| 11 | `update` with `feed_id` = `does_not_exist` | `unknown feed` |
| 12 | `is_at_least` on a feed that has not been updated | `feed has no value yet` |

### Sanity bounds case

1. `create_feed` with `feed_id` = `everest_bad_bounds`, the same `url`, `question`, and `unit` as Test 1, `step` = `1000`, `min_value` = `1000000`, `max_value` = `10000000` (that is 1.0 to 10.0).
2. `update` with `feed_id` = `everest_bad_bounds`.

Expected: the update does not succeed, because the extracted value is outside the allowed range. `get_latest` still shows `round` = `0`.

### Page without an answer

1. `create_feed` with `feed_id` = `no_answer`, `url` = `https://example.com`, `question` = `What is the price of Bitcoin in USD?`, `unit` = `USD`, `step` = `1000000`, `min_value` = `1000000`, `max_value` = `1000000000000`.
2. `update` with `feed_id` = `no_answer`.

Expected: the round fails, with `page did not contain an answer` or `evidence quote not found in page`, depending on what the model returns. `round` stays `0`.

## Notes for testers

- Use a page that states the number as plain text. Pages that load values with JavaScript or hide them behind logins will not work.
- A failed round near a rounding boundary is expected behavior, not a bug. Retry, or pick a step that puts the true value far from a boundary.
- Fast-moving values such as prices need a larger `step`, because validators fetch at slightly different moments.
- Bounds are a safety net, not a filter. Set them wide enough to cover legitimate changes.

## Use as a building block

Other contracts can call `is_at_least` or read `get_latest` to settle escrows, conditional payouts, or markets on a published number, knowing the stored value is the single canonical result of the round.
