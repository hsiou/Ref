import yaml

from endnote_mcp.config import Config


def test_config_load_reads_utf8_non_ascii_paths(tmp_path):
    xml_path = tmp_path / "我的坚果云" / "Writing" / "科研｜导出.xml"
    pdf_dir = tmp_path / "文献" / "My_Library.Data" / "PDF"
    db_path = tmp_path / "索引.db"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "endnote_xml": str(xml_path),
                "pdf_dir": str(pdf_dir),
                "db_path": str(db_path),
                "max_pdf_pages": 30,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    assert cfg.endnote_xml == xml_path.resolve()
    assert cfg.pdf_dir == pdf_dir.resolve()
    assert cfg.db_path == db_path.resolve()
    assert cfg.max_pdf_pages == 30
