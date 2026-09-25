from importlib import resources

from IPython import get_ipython

import freshrun


def test_extension_has_ipython_loader():
    assert callable(freshrun.load_ipython_extension)


def test_child_programs_are_packaged():
    package_files = resources.files("freshrun")

    startup = package_files.joinpath("child_startup.py")
    capture = package_files.joinpath("child_capture.py")

    assert startup.is_file()
    assert capture.is_file()

    assert "FreshChildMagics" in startup.read_text(
        encoding="utf-8"
    )

    assert "_capture_main" in capture.read_text(
        encoding="utf-8"
    )


def test_extension_registers_magic():
    ip = get_ipython()

    if ip is None:
        return

    freshrun.load_ipython_extension(ip)

    assert "freshrun" in ip.magics_manager.magics["line"]
