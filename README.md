# ToleranceOracle

A reusable GenLayer Intelligent Contract primitive for reading a numeric fact from a web page, with consensus based on numeric tolerance and evidence verification.

- Deployed contract (Studio): `0xa9478Bf7Fb0C06591b246Ae124b60eF8351e20dc`
- Explorer: `https://explorer-studio.genlayer.com/tx/0x5265ad6231eccfe17f0138d8ee9e0913ac9eaa4a96e31cdcea7cd01af31432e7`

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
| `create_feed(feed_id, url, question, unit, tolerance_bps, min_value, max_value)` | write | Registers a feed. `url` must start with `https://`. `tolerance_bps` is 1 to 5000. `min_value` and `max_value` are scaled by 1,000,000. |
| `update(feed_id)` | write | Runs a consensus round and stores the new value and evidence. Callable by anyone. |
| `get_latest(feed_id)` | view | Returns round, value, unit, evidence quote, source, and tolerance. |
| `get_config(feed_id)` | view | Returns the feed configuration. |

### Scaling reference

| Real value | Pass this number |
|---|---|
| 1 | `1000000` |
| 1,000 | `1000000000` |
| 10,000 | `10000000000` |

Tolerance is in basis points: `100` = 1%, `50` = 0.5%, `500` = 5%.

## Deploy

1. Open [GenLayer Studio](https://studio.genlayer.com) and paste `contracts/tolerance_oracle.py`.
2. Deploy with no constructor arguments.

## Testing guide

Run these in order in Studio's "Run and Debug" tab. A transaction can show `ACCEPTED` as its consensus status while its result is `ERROR`. Always check the **Result** field, not only the status.

### Test 1: create a feed (success)

Method: `create_feed`

| Argument | Value |
|---|---|
| `feed_id` | `everest_height` |
| `url` | `https://en.wikipedia.org/wiki/Mount_Everest` |
| `question` | `What is the elevation of Mount Everest above sea level in metres?` |
| `unit` | `metres` |
| `tolerance_bps` | `100` |
| `min_value` | `1000000000` |
| `max_value` | `10000000000` |

Expected: status `ACCEPTED`, result not `ERROR`, output `None`.

### Test 2: run a consensus round (success)

Method: `update`

| Argument | Value |
|---|---|
| `feed_id` | `everest_height` |

Expected: status `ACCEPTED`, result not `ERROR`. This takes longer than other calls because each validator fetches the page and runs the LLM.

### Test 3: read the result

Method: `get_latest` with `feed_id` = `everest_height`

Expected output (the evidence wording can differ slightly between runs, but it always contains `8,848.86`):

```json
{
  "round": 1,
  "value_scaled": 8848860000,
  "value": "8848.860000",
  "unit": "metres",
  "evidence": "... 8,848.86 m (29,031.7 ft) ...",
  "source": "https://en.wikipedia.org/wiki/Mount_Everest",
  "tolerance_bps": 100
}
```

### Test 4: read the config

Method: `get_config` with `feed_id` = `everest_height`

Expected: `owner` is the address that called `create_feed`, and `url`, `question`, `unit`, `tolerance_bps` (`100`), `min_value` (`1000000000`), and `max_value` (`10000000000`) match what you entered.

### Failure cases

Each of these should end with result `ERROR` and no stored value.

| # | Method and arguments | Expected error |
|---|---|---|
| 5 | `create_feed` with an empty `url`, or one starting with `http://` | `url must be https` |
| 6 | `create_feed` with `feed_id` = `everest_height` again | `feed already exists` |
| 7 | `create_feed` with `tolerance_bps` = `0` or `6000` | `tolerance_bps must be in 1..5000` |
| 8 | `create_feed` with `min_value` = `5000`, `max_value` = `1000` | `invalid bounds` |
| 9 | `update` with `feed_id` = `does_not_exist` | `unknown feed` |

### Sanity bounds case

1. `create_feed` with `feed_id` = `everest_bad_bounds`, the same `url`, `question`, and `unit` as Test 1, `tolerance_bps` = `100`, `min_value` = `1000000`, `max_value` = `10000000` (that is 1.0 to 10.0).
2. `update` with `feed_id` = `everest_bad_bounds`.

Expected: the update does not succeed, because 8848.86 is outside the allowed range. `get_latest` still shows `round` = `0` and `value_scaled` = `0`.

### Page without an answer

1. `create_feed` with `feed_id` = `no_answer`, `url` = `https://example.com`, `question` = `What is the price of Bitcoin in USD?`, `unit` = `USD`, `tolerance_bps` = `100`, `min_value` = `1000000`, `max_value` = `1000000000000`.
2. `update` with `feed_id` = `no_answer`.

Expected: the round fails, with `page did not contain an answer` or `evidence quote not found in page`, depending on what the model returns. `round` stays `0`.

## Notes for testers

- Use a page that states the number as plain text. Pages that load values with JavaScript or hide them behind logins will not work.
- Keep `tolerance_bps` realistic for the source. Fast-changing values such as prices need a higher tolerance (for example `100` to `500`) because validators fetch at slightly different moments.
- Bounds are a safety net, not a filter. Set them wide enough to cover legitimate changes.

## Use as a building block

Other contracts can use a feed as a threshold input, for example in escrows, conditional payouts, or markets that settle on a published number.
