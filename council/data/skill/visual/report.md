## How to report each object

For each object give:

- `page`: the page number written before its image.
- `type`: exactly one of `signature`, `unsigned_signature_block`, `initials`, `missing_initials`, `stamp`, `handwritten_correction`, `handwritten_note`, `checkbox`, `table`, `logo`.
- `box_2d`: `[ymin, xmin, ymax, xmax]`, normalized to 0-1000 over the page image; omit it for `missing_initials`.
- `text`: what it says, if you can read it; otherwise an empty string.
- `meaning`: one line on why it matters for the review.

## Rules

- Report only what you see on the page images; do not guess from the contract text.
- Never infer a missing signature unless there is an empty signature block: then report it as `unsigned_signature_block`.
- Report `missing_initials` only for a page without initials when other pages of the same contract are initialed.
- Copy handwriting and stamp text exactly; if a word is unreadable, write `[illegible]`.
- One object per item: two signatures are two objects.
- If the pages hold nothing from the list, return an empty `objects` list.

## Output

Return ONE JSON object and nothing else, without code fences:

{"objects": [{"page": 3, "type": "handwritten_correction", "box_2d": [412, 140, 438, 520], "text": "30 days -> 60 days", "meaning": "The payment term in clause 4.2 was changed by hand."}], "for_colleagues": "..."}

`for_colleagues` is at most three sentences on what changes for the review: for example a signature block left empty, a clause or an amount changed by hand, a stamp that dates or limits the agreement.
If nothing changes, write "The pages hold nothing that changes the review."
