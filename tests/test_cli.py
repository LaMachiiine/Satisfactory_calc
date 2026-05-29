from satisfactory_planner.ui.cli import main


def test_cli_forward(sample_docs, capsys):
    code = main(["forward", "Iron Plate", "20", "--docs", str(sample_docs)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Iron Plate" in out
    assert "8.00 MW" in out  # puissance totale (Constructor + Smelter à 100 %)


def test_cli_max(sample_docs, capsys):
    code = main(["max", "Iron Ingot", "--available", "Iron Ore=60", "--docs", str(sample_docs)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Iron Ingot" in out
    assert "60" in out  # sortie max = 60/min


def test_cli_forward_somersloops(sample_docs, capsys):
    # 30 lingots/min = 1 Smelter (1 slot). 1 sloop -> sortie x2.
    code = main([
        "forward", "Iron Ingot", "30", "--docs", str(sample_docs), "--somersloops", "1",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Somersloop" in out
    assert "60.00" in out  # sortie amplifiée


def test_cli_forward_distribute(sample_docs, capsys):
    code = main([
        "forward", "Iron Plate", "20", "--docs", str(sample_docs),
        "--distribute", "--belt", "3",
    ])
    assert code == 0
    assert "répartiteurs" in capsys.readouterr().out


def test_cli_forward_distribute_writes_files(sample_docs, tmp_path):
    code = main([
        "forward", "Iron Plate", "20", "--docs", str(sample_docs),
        "--distribute", "--out-dir", str(tmp_path),
    ])
    assert code == 0
    assert list(tmp_path.glob("*.dot"))
    assert list(tmp_path.glob("*.json"))


def test_cli_forward_with_alternates(sample_docs, capsys):
    # 65 lingots/min : avec --alternates, min_raw choisit Pure Iron Ingot.
    code = main(
        ["forward", "Iron Ingot", "65", "--docs", str(sample_docs), "--alternates"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Pure Iron Ingot" in out
