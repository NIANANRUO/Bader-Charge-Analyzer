import pandas as pd

from gui.worker import AnalysisWorker


def test_worker_target_does_not_trim_full_results(tmp_path, monkeypatch):
    for name in ("POSCAR", "POTCAR", "ACF.dat"):
        (tmp_path / name).write_text("fixture", encoding="utf-8")

    monkeypatch.setattr(
        "gui.worker.VaspParser.parse_structure",
        lambda _path: (["site1", "site2"], ["Li", "O"]),
    )
    monkeypatch.setattr(
        "gui.worker.VaspParser.parse_potcar_zval",
        lambda _path: ({"Li": 1, "O": 6}, [1, 6], ["Li", "O"]),
    )
    monkeypatch.setattr(
        "gui.worker.VaspParser.parse_acf",
        lambda _path: pd.DataFrame(
            {
                "Atom": [1, 2],
                "X": [0.0, 1.0],
                "Y": [0.0, 1.0],
                "Z": [0.0, 1.0],
                "CHARGE": [1.2, 5.8],
                "Min_Dist": [0.1, 0.2],
                "Volume": [10.0, 11.0],
            }
        ),
    )

    worker = AnalysisWorker(str(tmp_path), {"target": "1"})
    emitted = []
    worker.finished.connect(lambda struct, df, err: emitted.append((struct, df, err)))
    worker.run()

    assert emitted[0][2] is None
    assert emitted[0][1]["Atom"].tolist() == [1, 2]


def test_worker_emits_thread_completed_after_success(tmp_path, monkeypatch):
    for name in ("POSCAR", "POTCAR", "ACF.dat"):
        (tmp_path / name).write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(
        "gui.worker.VaspParser.parse_structure",
        lambda _path: (["site"], ["Li"]),
    )
    monkeypatch.setattr(
        "gui.worker.VaspParser.parse_potcar_zval",
        lambda _path: ({"Li": 1}, [1], ["Li"]),
    )
    monkeypatch.setattr(
        "gui.worker.VaspParser.parse_acf",
        lambda _path: pd.DataFrame({
            "Atom": [1], "X": [0.0], "Y": [0.0], "Z": [0.0],
            "CHARGE": [1.0], "Min_Dist": [0.1], "Volume": [1.0],
        }),
    )
    worker = AnalysisWorker(str(tmp_path), {"target": "1"})
    completed = []
    worker.thread_completed.connect(lambda: completed.append(True))

    worker.run()

    assert completed == [True]


def test_worker_emits_thread_completed_after_error(tmp_path):
    worker = AnalysisWorker(str(tmp_path), {"target": ""})
    completed = []
    worker.thread_completed.connect(lambda: completed.append(True))

    worker.run()

    assert completed == [True]

