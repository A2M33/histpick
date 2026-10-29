from histpick.picker import PickerState, one_line


def state():
    # newest first, like the real list
    return PickerState(["git push", "git commit -m x", "npm test", "git add ."])


def test_result_is_in_run_order():
    s = state()
    s.toggle()  # git push (newest)
    s.move(2)
    s.toggle()  # git add . (oldest)
    assert s.result() == ["git add .", "git push"]


def test_filter_and_toggle_all():
    s = state()
    s.type("git")
    assert [s.items[i] for i in s.visible()] == ["git push", "git commit -m x", "git add ."]
    s.toggle_all_visible()
    assert s.result() == ["git add .", "git commit -m x", "git push"]
    s.toggle_all_visible()
    assert s.result() == []


def test_filter_is_case_insensitive_and_backspace_resets():
    s = state()
    s.type("NPM")
    assert len(s.visible()) == 1
    s.backspace(), s.backspace(), s.backspace()
    assert len(s.visible()) == 4


def test_cursor_stays_in_range():
    s = state()
    s.move(-5)
    assert s.cursor == 0
    s.move(99)
    assert s.cursor == 3
    s.type("zzz")
    s.move(1)
    assert s.cursor == 0
    s.toggle()  # nothing visible: no crash
    assert s.result() == []


def test_scroll_follows_cursor():
    s = PickerState([str(i) for i in range(50)])
    s.move(20)
    s.scroll(10)
    assert s.top == 11
    s.move(-20)
    s.scroll(10)
    assert s.top == 0


def test_one_line():
    assert one_line("a\nb\nc", 80) == "a  (+2 lines)"
    assert one_line("x" * 20, 10) == "x" * 9 + "…"


def test_space_goes_into_the_filter_and_words_are_and_terms():
    from histpick.picker import _CHARS

    assert _CHARS.get(" ", " ") == " "  # space is typed, not a choose key
    s = state()
    for ch in "git m":
        s.type(ch)
    assert s.query == "git m"
    assert [s.items[i] for i in s.visible()] == ["git commit -m x"]
    s = state()
    for ch in "x git":  # order of words doesn't matter
        s.type(ch)
    assert [s.items[i] for i in s.visible()] == ["git commit -m x"]


def test_review_reorders_and_removes():
    from histpick.picker import PickerState

    # history was cd, npm i, cd: dedupe keeps the latest cd, so run order is npm i, cd
    s = PickerState(["cd app", "npm i"])
    s.toggle_all_visible()
    r = s.review()
    assert r.result() == ["npm i", "cd app"]
    r.move(1)
    r.shift(-1)  # move "cd app" to the top
    assert r.result() == ["cd app", "npm i"]
    assert r.cursor == 0
    r.shift(-1)  # already at the top: nothing happens
    assert r.result() == ["cd app", "npm i"]
    r.move(1)
    r.remove()
    assert r.result() == ["cd app"] and r.cursor == 0
    r.remove()
    r.remove()  # empty: no crash
    assert r.result() == []


def test_review_order_survives_going_back():
    s = state()
    s.toggle()  # git push
    s.toggle()  # git commit -m x
    r = s.review()
    assert r.result() == ["git commit -m x", "git push"]
    r.shift(1)
    s.back_from(r)
    s.move(1)
    s.toggle()  # git add .
    assert s.review().result() == ["git push", "git commit -m x", "git add ."]


class ScriptedKeys:
    def __init__(self, keys):
        self.keys = iter(keys)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def read(self):
        return next(self.keys)


def run_pick(monkeypatch, items, keys):
    from histpick import picker

    monkeypatch.setattr(picker, "_Keys", lambda: ScriptedKeys(keys))
    monkeypatch.setenv("TERM", "xterm")
    return picker.pick(items)


def test_pick_goes_through_review(monkeypatch, capsys):
    from histpick.picker import DOWN, ENTER, ESC, TAB

    items = ["git push", "git commit -m x", "npm test"]
    assert run_pick(monkeypatch, items, [TAB, TAB, ENTER, "d", ENTER]) == ["git push", "git commit -m x"]
    # Esc in review goes back to the list, a removed command stays unchosen
    assert run_pick(monkeypatch, items, [TAB, TAB, ENTER, "x", ESC, DOWN, DOWN, TAB, ENTER, ENTER]) == \
        ["git push", "npm test"]
    assert "review" in capsys.readouterr().out
