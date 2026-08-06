from importlib import import_module


def test_cellforge_domain_is_importable() -> None:
    module = import_module("cellforge_domain")

    assert module.__name__ == "cellforge_domain"
