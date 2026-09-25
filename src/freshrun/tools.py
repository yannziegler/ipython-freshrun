from collections.abc import Mapping

from IPython.core.magic import Magics, line_magic, magics_class


LOCALS_DICT_NAME = "_exception_locals"


@magics_class
class InjectPullMagics(Magics):

    @line_magic
    def inject(self, line: str) -> None:
        """Inject all entries from a mapping into the IPython namespace.

        Usage:
            %inject my_dict
        """
        expression = line.strip()

        if not expression:
            print("Usage: %inject <mapping>")
            return

        mapping = self.shell.ev(expression)

        if not isinstance(mapping, Mapping):
            print(
                f"{expression!r} is not a mapping "
                f"(got {type(mapping).__name__})"
            )
            return

        self.shell.user_ns.update(mapping)

    @line_magic
    def pull(self, line: str) -> None:
        """Pull one entry from _exception_locals into the IPython namespace.

        Usage:
            %pull key_name
        """
        key = line.strip()

        if not key:
            print("Usage: %pull <function/method name from " \
                  f"{LOCALS_DICT_NAME}.keys()>")
            return

        if LOCALS_DICT_NAME not in self.shell.user_ns:
            print("There are no locals to pull into the current namespace, ")
            print(f"locals dict {LOCALS_DICT_NAME} does not exist.")
            return

        mapping = self.shell.user_ns[LOCALS_DICT_NAME]

        if not isinstance(mapping, Mapping):
            print(
                f"{LOCALS_DICT_NAME!r} exists but is not a mapping "
                f"(got {type(mapping).__name__})."
            )
            return

        if key not in mapping:
            print(f"Function/method name {key!r} not found in {LOCALS_DICT_NAME}.")
            print(f"You may want to double check {LOCALS_DICT_NAME}.keys()")
            return

        self.shell.user_ns.update(mapping[key])
