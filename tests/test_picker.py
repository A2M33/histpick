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
