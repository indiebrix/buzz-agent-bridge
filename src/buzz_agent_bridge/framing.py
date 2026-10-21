"""Buzz desktop-v0.5.28 framing. Extract identifiers, never trust prompt bodies."""
import re

CURRENT = ("buzz-event", "buzz-events", "new-message-arrived-while-you-were-working",
           "new-request-supersedes-previous")


def source_ids(blocks):
    if not isinstance(blocks, list) or len(blocks) > 100:
        raise ValueError("Invalid prompt blocks")
    texts = []
    for block in blocks:
        if isinstance(block, str):
            text = block
        elif getattr(block, "type", None) == "text":
            text = block.text
        else:
            raise ValueError("Only Buzz text envelopes are supported")
        texts.append(text)
    if sum(len(text.encode()) for text in texts) > 262144:
        raise ValueError("Prompt too large")
    sections = []
    for text in texts:
        opening = re.match(r"^<([a-z-]+)([^>\n]*)>\n", text)
        if opening is None or opening[1] not in CURRENT:
            continue  # Prior context, instructions and old events are not requests.
        tag, attributes = opening[1], opening[2]
        ending = f"\n</{tag}>"
        if not text.endswith(ending):
            raise ValueError("Malformed Buzz section")
        body = text[opening.end():-len(ending)]
        if tag == "buzz-event":
            if not re.fullmatch(r' type="[^"\n]*"', attributes):
                raise ValueError("Invalid single-event envelope")
            match = re.match(r"^Event ID: ([0-9a-f]{64})\n", body)
            if match is None:
                raise ValueError("Missing source ID")
            ids = [match[1]]
        else:
            count = re.fullmatch(r' count="([1-9][0-9]?)"', attributes)
            if attributes and count is None:
                raise ValueError("Invalid batch metadata")
            expected = int(count[1]) if count else 1
            if not 1 <= expected <= 50:
                raise ValueError("Batch limit exceeded")
            found = re.findall(r"(?m)^--- Event ([1-9][0-9]?) \([^\n]*\) ---\n"
                               r"Event ID: ([0-9a-f]{64})\n", body)
            if ([int(number) for number, _ in found] != list(range(1, expected + 1))
                    or not body.startswith("--- Event 1 (")):
                # Embedded fake event delimiters make a batch ambiguous, so fail
                # closed. Every extracted ID is subsequently fetched and verified.
                raise ValueError("Ambiguous batch")
            ids = [ident for _, ident in found]
        sections.append(ids)
    if len(sections) != 1 or len(set(sections[0])) != len(sections[0]):
        raise ValueError("Expected one unambiguous current-event section")
    return sections[0]
