import json

from g1.summary import report


def write(folder, name, rows):
    (folder / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def row(i, correct, tokens):
    return {
        "id": f"p{i}",
        "correct": correct,
        "tokens_generated": tokens,
        "tokens_read": 50,
        "seconds": 2.0,
        "truncated": 0,
        "latent_positions": 0,
    }


def test_the_report_for_the_ticket(tmp_path):
    write(tmp_path, "text", [row(0, True, 400), row(1, True, 600)])
    write(tmp_path, "telepathy", [row(0, True, 100), row(1, True, 100)])
    write(tmp_path, "no_thoughts", [row(0, True, 90), row(1, False, 90)])
    (tmp_path / "memory.json").write_text(json.dumps({"ok": True, "two_models_weights_gb": 101.6}))

    text = report(tmp_path)

    assert "**G1 passes**" in text
    assert "−80%" in text  # 200 tokens in telepathy against 1,000 in text
    assert "demonstrated" in text
    assert "101.6 GB" in text
    assert "can be said" in text  # more than 80 GB: the script's line about the H100
    assert "cannot be said" not in text


def test_without_memory_the_report_says_so(tmp_path):
    for name in ("text", "telepathy", "no_thoughts"):
        write(tmp_path, name, [row(0, True, 100)])
    assert "the memory measurement is missing" in report(tmp_path)


def test_an_interrupted_run_is_reported_on_the_problems_finished_in_the_three_modes(tmp_path):
    write(tmp_path, "text", [row(0, True, 400), row(1, True, 600)])
    write(tmp_path, "telepathy", [row(0, True, 100), row(1, True, 100)])
    write(tmp_path, "no_thoughts", [row(0, True, 90)])
    (tmp_path / "environment.json").write_text(json.dumps({"problems": 100}))

    text = report(tmp_path)

    assert "Partial: 1 problem out of 100" in text
    assert "−75%" in text  # only p0: 100 tokens in telepathy against 400 in text
