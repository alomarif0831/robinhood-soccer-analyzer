from datetime import date

from rsa.interactive import build_argv, run_menu


def _inputs(*answers):
    it = iter(answers)
    return lambda prompt: next(it)


def test_build_argv_demo_and_series():
    assert build_argv("1") == ["demo"]
    assert build_argv("4") == ["series"]
    assert build_argv("h") == ["--help"]
    assert build_argv("zzz") is None


def test_build_argv_live_run_uses_defaults_when_blank():
    argv = build_argv("2", _inputs("", "", "", "", "", "", ""), today=date(2026, 9, 6))
    assert argv[:2] == ["run", "--leagues"]
    assert "--start" in argv and argv[argv.index("--start") + 1] == "2026-07-20"
    assert argv[argv.index("--end") + 1] == "2026-09-06"
    assert argv[argv.index("--fees") + 1] == "robinhood" and argv[argv.index("--fill") + 1] == "ask"


def test_build_argv_backtest_with_answers_and_reprompt_on_bad_choice():
    argv = build_argv("3", _inputs("data/x", "nope", "kalshi", "0.05", "last"))
    assert argv == ["backtest", "--data-dir", "data/x", "--fees", "kalshi", "--min-edge", "0.05", "--fill", "last"]


def test_run_menu_dispatches_and_quits():
    calls = []

    def runner(argv):
        calls.append(argv)
        return 0

    rc = run_menu(runner, _inputs("1", "", "q"))
    assert rc == 0 and calls == [["demo"]]
    # errors inside a command are reported, not raised, so the window stays open
    rc = run_menu(lambda argv: (_ for _ in ()).throw(RuntimeError("boom")), _inputs("4", "", "q"))
    assert rc == 1


def _inputs_then_eof(*answers):
    it = iter(answers)

    def fn(prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return fn


def test_run_menu_treats_eof_anywhere_as_quit():
    calls = []
    # EOF at the "Press Enter to return" prompt after a successful command
    assert run_menu(lambda a: calls.append(a) or 0, _inputs_then_eof("1")) == 0 and calls == [["demo"]]
    # EOF in the middle of the live-run questionnaire
    assert run_menu(lambda a: 0, _inputs_then_eof("2", "epl")) == 0
    # EOF at the very first prompt
    assert run_menu(lambda a: 0, _inputs_then_eof()) == 0


def test_bare_enter_reshows_menu_instead_of_quitting():
    calls = []
    rc = run_menu(lambda a: calls.append(a) or 0, _inputs("", "", "1", "", "q"))
    assert rc == 0 and calls == [["demo"]]


def test_keyboard_interrupt_inside_command_is_reported():
    def runner(argv):
        raise KeyboardInterrupt

    assert run_menu(runner, _inputs("1", "", "q")) == 130


def test_pause_if_interactive_never_blocks_without_tty(monkeypatch):
    import io
    import sys

    from rsa.interactive import pause_if_interactive

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # not a tty
    pause_if_interactive()  # returns immediately
    monkeypatch.setattr(sys, "stdin", None)
    pause_if_interactive()
