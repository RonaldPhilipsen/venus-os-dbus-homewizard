import homewizard


def test_version_is_a_non_empty_string():
    assert isinstance(homewizard.__version__, str) and homewizard.__version__
