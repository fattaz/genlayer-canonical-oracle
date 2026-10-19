# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from dataclasses import dataclass
import json
import re

SCALE_DIGITS = 6
SCALE = 10**SCALE_DIGITS
MAX_PAGE_CHARS = 12000


@allow_storage
@dataclass
class Feed:
    owner: Address
    url: str
    question: str
    unit: str
    step: u256
    min_value: u256
    max_value: u256
    round: u256
    latest_value: u256
    latest_evidence: str


def _to_scaled(raw) -> int:
    s = str(raw).strip().replace(",", "").replace("$", "").replace("%", "")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        raise gl.vm.UserError("extracted value is not a plain non-negative number")
    whole, _, frac = s.partition(".")
    frac = (frac + "0" * SCALE_DIGITS)[:SCALE_DIGITS]
    return int(whole) * SCALE + int(frac)


def _canonical(scaled: int, step: int) -> int:
    return ((scaled + step // 2) // step) * step


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _fetch_and_extract(url: str, question: str, unit: str, step: int):
    page = gl.nondet.web.render(url, mode="text")[:MAX_PAGE_CHARS]

    prompt = f"""You extract ONE number from a web page.

Question: {question}
Unit: {unit}

Rules:
- Use ONLY the page text below. Never use outside knowledge.
- "value" must be a plain non-negative number, no units or symbols.
- "evidence" must be ONE sentence or line copied EXACTLY from the page
  that contains the number you chose.
- If the page does not answer the question, return {{"value": "", "evidence": ""}}.

Respond ONLY with JSON: {{"value": "<number>", "evidence": "<exact quote>"}}

PAGE:
{page}
"""
    out = gl.nondet.exec_prompt(prompt, response_format="json")
    if isinstance(out, str):
        out = json.loads(out)

    value = str(out.get("value", "")).strip()
    evidence = str(out.get("evidence", "")).strip()
    if not value or not evidence:
        raise gl.vm.UserError("page did not contain an answer")

    page_norm = _norm(page)
    if _norm(evidence) not in page_norm:
        raise gl.vm.UserError("evidence quote not found in page")

    canon = _canonical(_to_scaled(value), step)
    return {"value": str(canon), "evidence": evidence}, page_norm


class CanonicalOracle(gl.Contract):
    feeds: TreeMap[str, Feed]

    def __init__(self):
        pass

    @gl.public.write
    def create_feed(
        self,
        feed_id: str,
        url: str,
        question: str,
        unit: str,
        step: int,
        min_value: int,
        max_value: int,
    ) -> None:
        if feed_id in self.feeds:
            raise gl.vm.UserError("feed already exists")
        if not url.startswith("https://"):
            raise gl.vm.UserError("url must be https")
        if step < 1:
            raise gl.vm.UserError("step must be at least 1")
        if not (0 <= min_value < max_value):
            raise gl.vm.UserError("invalid bounds")
        if step > max_value - min_value:
            raise gl.vm.UserError("step larger than bounds range")

        self.feeds[feed_id] = Feed(
            owner=gl.message.sender_address,
            url=url,
            question=question,
            unit=unit,
            step=u256(step),
            min_value=u256(min_value),
            max_value=u256(max_value),
            round=u256(0),
            latest_value=u256(0),
            latest_evidence="",
        )

    @gl.public.write
    def update(self, feed_id: str) -> None:
        if feed_id not in self.feeds:
            raise gl.vm.UserError("unknown feed")
        feed = self.feeds[feed_id]

        url = feed.url
        question = feed.question
        unit = feed.unit
        step = int(feed.step)
        lo = int(feed.min_value)
        hi = int(feed.max_value)

        def leader_fn():
            result, _ = _fetch_and_extract(url, question, unit, step)
            return result

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                try:
                    _fetch_and_extract(url, question, unit, step)
                    return False
                except Exception:
                    return True

            lead = leaders_res.calldata
            try:
                mine, my_page = _fetch_and_extract(url, question, unit, step)
                lead_value = int(lead["value"])
                my_value = int(mine["value"])
            except Exception:
                return False

            if lead_value % step != 0:
                return False
            if not (lo <= lead_value <= hi):
                return False
            if lead_value != my_value:
                return False
            return _norm(lead["evidence"]) in my_page

        agreed = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        value = int(agreed["value"])
        if value % step != 0 or not (lo <= value <= hi):
            raise gl.vm.UserError("value outside sanity bounds")

        feed.latest_value = u256(value)
        feed.latest_evidence = agreed["evidence"]
        feed.round = u256(int(feed.round) + 1)

    @gl.public.view
    def get_latest(self, feed_id: str) -> dict:
        if feed_id not in self.feeds:
            raise gl.vm.UserError("unknown feed")
        f = self.feeds[feed_id]
        v = int(f.latest_value)
        return {
            "round": int(f.round),
            "value_scaled": v,
            "value": f"{v // SCALE}.{str(v % SCALE).zfill(SCALE_DIGITS)}",
            "unit": f.unit,
            "evidence": f.latest_evidence,
            "source": f.url,
            "step": int(f.step),
        }

    @gl.public.view
    def is_at_least(self, feed_id: str, threshold: int) -> bool:
        if feed_id not in self.feeds:
            raise gl.vm.UserError("unknown feed")
        f = self.feeds[feed_id]
        if int(f.round) == 0:
            raise gl.vm.UserError("feed has no value yet")
        return int(f.latest_value) >= threshold

    @gl.public.view
    def get_config(self, feed_id: str) -> dict:
        if feed_id not in self.feeds:
            raise gl.vm.UserError("unknown feed")
        f = self.feeds[feed_id]
        return {
            "owner": f.owner.as_hex,
            "url": f.url,
            "question": f.question,
            "unit": f.unit,
            "step": int(f.step),
            "min_value": int(f.min_value),
            "max_value": int(f.max_value),
        }
