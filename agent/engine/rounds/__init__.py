"""Round-type plugin registrations. Importing this package registers all
built-in round types (T19); adding a round type = adding a module here."""

from engine.rounds import basic, behavioral, case, coding, design  # noqa: F401
