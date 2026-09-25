from freshrun.freshrun import _find_script_argument


def test_find_script_argument_plain():
    assert _find_script_argument(["script.py"]) == "script.py"


def test_find_script_argument_with_script_arguments():
    assert _find_script_argument(
        ["script.py", "one", "two"]
    ) == "script.py"


def test_find_script_argument_debug():
    assert _find_script_argument(
        ["-d", "script.py"]
    ) == "script.py"


def test_find_script_argument_interactive():
    assert _find_script_argument(
        ["-i", "script.py"]
    ) == "script.py"


def test_find_script_argument_namespace():
    assert _find_script_argument(
        ["-n", "script.py"]
    ) == "script.py"


def test_find_script_argument_after_double_dash():
    assert _find_script_argument(
        ["--", "script.py"]
    ) == "script.py"


def test_find_script_argument_module_is_unsupported():
    assert _find_script_argument(
        ["-m", "some.module"]
    ) is None


def test_find_script_argument_missing_after_double_dash():
    assert _find_script_argument(["--"]) is None


def test_find_script_argument_skips_options_with_arguments():
    assert _find_script_argument(
        ["-b", "10", "script.py"]
    ) == "script.py"
