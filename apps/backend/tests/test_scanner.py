from nyanko_api.scanner import iter_video_files, parse_file


def test_iter_video_files_respects_recursive_flag(tmp_path):
    (tmp_path / "Frieren - 01 [1080p].mkv").write_text("x")
    (tmp_path / "notes.txt").write_text("x")
    sub = tmp_path / "season2"
    sub.mkdir()
    (sub / "Frieren - 13.mp4").write_text("x")

    recursive = list(iter_video_files([{"path": str(tmp_path), "recursive": True}]))
    flat = list(iter_video_files([{"path": str(tmp_path), "recursive": False}]))

    assert len(recursive) == 2  # video files only, including the subfolder
    assert len(flat) == 1  # subfolder skipped, .txt ignored


def test_iter_video_files_skips_missing_folder():
    assert list(iter_video_files([{"path": "/no/such/folder", "recursive": True}])) == []


def test_iter_video_files_skips_manga_folders(tmp_path):
    # El escaneo de anime no tiene por qué mover el disco de una carpeta de manga:
    # es el hallazgo #2 del UAT de la fase 03.
    carpetas = {}
    for kind in ("anime", "manga", "ambas"):
        carpeta = tmp_path / kind
        carpeta.mkdir()
        (carpeta / f"Frieren - 01 [{kind}].mkv").write_text("x")
        carpetas[kind] = carpeta

    encontrados = list(iter_video_files([
        {"path": str(carpetas["anime"]), "recursive": True, "kind": "anime"},
        {"path": str(carpetas["manga"]), "recursive": True, "kind": "manga"},
        {"path": str(carpetas["ambas"]), "recursive": True, "kind": "ambas"},
    ]))

    assert len(encontrados) == 2
    assert any(str(carpetas["anime"]) in path for path in encontrados)
    assert any(str(carpetas["ambas"]) in path for path in encontrados)
    assert not any(str(carpetas["manga"]) in path for path in encontrados)


def test_iter_video_files_accepts_folder_without_kind(tmp_path):
    # Tipo ausente ⇒ ambas: el mismo criterio que la migración v9→v10.
    (tmp_path / "Frieren - 01.mkv").write_text("x")

    assert len(list(iter_video_files([{"path": str(tmp_path), "recursive": True}]))) == 1


def test_parse_file_extracts_title_and_episode(tmp_path):
    title, episode = parse_file(str(tmp_path / "[Group] Sousou no Frieren - 12 [1080p].mkv"))
    assert title and "frieren" in title.lower()
    assert episode == 12


def test_parse_file_falls_back_to_series_folder_for_bare_filenames():
    # Episode files named only by number take their title from the series folder,
    # skipping season-only folders in between.
    title, episode = parse_file("/anime/Sousou no Frieren/01.mkv")
    assert title and "frieren" in title.lower()
    assert episode == 1

    title, episode = parse_file("/anime/One Piece/Season 1/12.mkv")
    assert title and "one piece" in title.lower()
    assert episode == 12
