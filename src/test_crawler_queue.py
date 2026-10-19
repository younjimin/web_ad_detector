from crawler import FairQueue, url_template

def test_template_digits_and_query_order():
    a = url_template("https://x.kr/bbs/view.do?nttId=123&bbsId=BBSMSTR_0004")
    b = url_template("https://x.kr/bbs/view.do?bbsId=BBSMSTR_0009&nttId=77")
    assert a == b == "/bbs/view.do?bbsId=BBSMSTR_#&nttId=#"
def test_template_different_pages_differ():
    assert url_template("https://x.kr/bbs/list.do?bbsId=1") != url_template("https://x.kr/bbs/view.do?bbsId=1")
def test_template_no_query():
    assert url_template("https://x.kr/a/b2/c.do") == "/a/b#/c.do"
def test_fair_order_mixes_types():
    q = FairQueue()
    for i in range(10):
        q.append((f"https://x.kr/bbs/list.do?bbsId={i}&page=1", f"l{i}"))
    q.append(("https://x.kr/bbs/view.do?nttId=1", "v1"))
    q.append(("https://x.kr/bbs/view.do?nttId=2", "v2"))
    q.append(("https://x.kr/about.do", "a"))
    first = [q.popleft()[1] for _ in range(6)]
    assert "v1" in first and "a" in first          # 6번 안에 서로 다른 유형이 모두 나온다
def test_everything_is_eventually_returned():
    q = FairQueue()
    urls = [f"https://x.kr/p/{i}.do" for i in range(5)] + [f"https://x.kr/q.do?id={i}" for i in range(7)]
    for i, u in enumerate(urls):
        q.append((u, str(i)))
    out = []
    while len(q):
        out.append(q.popleft()[1])
    assert sorted(out) == sorted(str(i) for i in range(len(urls)))
def test_fifo_within_same_template():
    q = FairQueue()
    q.append(("https://x.kr/v.do?id=1", "k1")); q.append(("https://x.kr/v.do?id=2", "k2"))
    assert [q.popleft()[1], q.popleft()[1]] == ["k1", "k2"]
def test_empty_raises():
    try:
        FairQueue().popleft()
    except IndexError:
        return
    raise AssertionError

def test_new_family_is_not_starved_by_many_singletons():
    """실제 행안부 로그에서 본 현상: 서로 다른 단독 페이지 수십 개가 먼저 쌓여 있어도
    새로 발견된 게시글 상세 가족이 몇 번 안에 방문되어야 한다."""
    q = FairQueue()
    for i in range(40):
        q.append((f"https://x.kr/menu/page{chr(97 + i % 26)}{chr(97 + i // 26)}x.do", f"s{i}"))
    for j in range(10):
        q.append((f"https://x.kr/bbs/view.do?nttId={j}", f"v{j}"))
    first = [q.popleft()[1] for _ in range(10)]
    assert sum(k.startswith("v") for k in first) >= 3


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try: f(); print("PASS ", n)
        except Exception as e: bad += 1; print("FAIL ", n, "->", type(e).__name__, e)
    print(f"\n{len(tests)-bad}/{len(tests)} passed")

