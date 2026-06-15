from evermem.cli import main


def test_remember_recall_roundtrip(tmp_path, capsys):
    db = str(tmp_path / "memory.db")

    assert main(["remember", "меня зовут Алекс, я живу в Минске", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "stored turn" in out

    assert main(["recall", "где живёт пользователь?", "--db", db, "--session", "other"]) == 0
    out = capsys.readouterr().out
    assert "[MEMORY]" in out
    assert "минск" in out.lower()


def test_import_and_profile(tmp_path, capsys):
    db = str(tmp_path / "memory.db")
    doc = tmp_path / "note.txt"
    doc.write_text("Сумма по договору 47 равна 9000 рублей.", encoding="utf-8")

    assert main(["import", str(doc), "--db", db]) == 0
    out = capsys.readouterr().out
    assert "OK" in out and "blocks" in out

    assert main(["remember", "я люблю кофе", "--db", db]) == 0
    capsys.readouterr()
    assert main(["profile", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "likes" in out


def test_import_unsupported_file_sets_exit_code(tmp_path, capsys):
    db = str(tmp_path / "memory.db")
    bad = tmp_path / "binary.exe"
    bad.write_bytes(b"MZ")
    assert main(["import", str(bad), "--db", db]) == 1
    err = capsys.readouterr().err
    assert "SKIP" in err


def test_stats_outputs_counters(tmp_path, capsys):
    db = str(tmp_path / "memory.db")
    main(["remember", "I love black coffee", "--db", db])
    capsys.readouterr()
    assert main(["stats", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "turns" in out


def test_recall_budget_caps_output(tmp_path, capsys):
    db = str(tmp_path / "memory.db")
    for i in range(10):
        main(["remember", f"факт номер {i}: я люблю продукт номер {i}", "--db", db])
    capsys.readouterr()
    assert main(["recall", "что я люблю?", "--db", db, "--budget", "300", "--session", "x"]) == 0
    out = capsys.readouterr().out.strip()
    assert len(out) <= 300
    assert out.endswith("[/MEMORY]")
