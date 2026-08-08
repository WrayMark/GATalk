from pathlib import Path

from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore


def test_library_import_keeps_one_canonical_item_across_collections(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "中文 资料库", "美术资料")
    colour = library.add_collection("色彩")
    lighting = library.add_collection("灯光")
    source = tmp_path / "参考 图.png"
    source.write_bytes(b"not-a-decoded-image-but-original-bytes")

    first = library.import_file(source, collection_ids=(colour.collection_id,))
    second = library.import_file(source, collection_ids=(lighting.collection_id,))

    assert first.item_id == second.item_id
    assert len(library.state.items) == 1
    assert set(library.state.memberships[first.item_id]) == {
        colour.collection_id,
        lighting.collection_id,
    }
    assert library.resolve_item_path(first).read_bytes() == source.read_bytes()


def test_library_search_and_unknown_tags_survive_reopen(tmp_path: Path):
    root = tmp_path / "library"
    library = KnowledgeLibraryStore.create(root, "案例库")
    source = tmp_path / "雾景.webp"
    source.write_bytes(b"webp-source-bytes")
    item = library.import_file(source)
    library.update_item(
        item.__class__(
            **{
                **item.to_dict(),
                "creator": "示例作者",
                "tags": ("薄雾", "自定义标签-01"),
                "notes": "观察空气透视。",
            }
        )
    )

    reopened = KnowledgeLibraryStore.open(root)

    assert reopened.items_for(search="自定义标签-01")[0].creator == "示例作者"
    assert reopened.integrity_issues() == ()


def test_library_links_are_recorded_without_network_fetch(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "library", "资料库")
    item = library.add_link("https://example.com/case", "案例来源")

    assert item.source_kind == "url"
    assert item.local_relative_path is None
    assert item.provenance_status == "unverified"


def test_library_export_excludes_asset_bytes(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "library", "资料库")
    source = tmp_path / "source.jpg"
    source.write_bytes(b"RAW_BINARY_PAYLOAD_6731")
    library.import_file(source)
    report = library.export_catalog(tmp_path / "catalog.json")

    text = report.read_text(encoding="utf-8")
    assert "gatalk.knowledge_catalog_export" in text
    assert "RAW_BINARY_PAYLOAD_6731" not in text
