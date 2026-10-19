#!/usr/bin/env python3
"""Masque smoke test. Needs only Python 3 (standard library) and the site's own requirements (pip install -r requirements.txt).

    python3 tests/smoke.py

starts a THROWAWAY copy of the site (python3 serve.py on a free port, fresh data folder, test settings), runs every check and stops it.
To test a server that is already running instead:

    python3 tests/smoke.py http://127.0.0.1:8080/ testadmin adminpass123

That server needs the same test settings: ADMIN_USER=testadmin ADMIN_PASSWORD=adminpass123 AUTOHIDE=3 AUTOHIDE_AGE=0 NEWACCT_SECS=0 BACKGROUND=off.

It creates 4 accounts (the sign-up limit is 5 per hour per IP), so use a fresh server for every run.
"""
import atexit, http.cookiejar, json, os, re, secrets, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestServer:
    """A throwaway Masque (serve.py, fresh DATA_DIR, test settings) for the length of the run."""
    ADMIN, ADMINPW = "testadmin", "adminpass123"

    def __init__(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.data = tempfile.mkdtemp(prefix="masque-smoke-")
        env = dict(os.environ, DATA_DIR=self.data, PORT=str(self.port), ADMIN_USER=self.ADMIN, ADMIN_PASSWORD=self.ADMINPW,
                   AUTOHIDE="3", AUTOHIDE_AGE="0", NEWACCT_SECS="0", BACKGROUND="off")
        self.log = open(os.path.join(self.data, "serve.log"), "w+")
        self.proc = subprocess.Popen([sys.executable, "serve.py"], cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        atexit.register(self.stop)
        for _ in range(150):
            try:
                urllib.request.urlopen(self.url + "?a=mtstat", timeout=2).read()
                return
            except Exception:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.2)
        self.log.flush()
        self.log.seek(0)
        raise SystemExit("could not start serve.py (are the requirements installed?)\n" + self.log.read()[-3000:])

    @property
    def url(self):
        return "http://127.0.0.1:%d/" % self.port

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.data, ignore_errors=True)


if len(sys.argv) > 1:
    BASE = sys.argv[1].rstrip("/") + "/"
    ADMIN = sys.argv[2] if len(sys.argv) > 2 else TestServer.ADMIN
    ADMINPW = sys.argv[3] if len(sys.argv) > 3 else TestServer.ADMINPW
else:
    _srv = TestServer()
    BASE, ADMIN, ADMINPW = _srv.url, TestServer.ADMIN, TestServer.ADMINPW
RC_RE = re.compile(r"^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$")
passed = failed = 0


def check(name, ok, extra=""):
    global passed, failed
    if ok:
        passed += 1
        print("  ok   " + name)
    else:
        failed += 1
        print("  FAIL " + name + (" -> " + str(extra) if extra else ""))


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""
        self.refresh()

    def raw(self, a, data=None, extra=""):
        url = BASE + "?a=" + a + extra
        req = urllib.request.Request(url)
        if data is not None:
            req = urllib.request.Request(url, urllib.parse.urlencode(data).encode(), {"X-CSRF": self.csrf})
        try:
            r = self.op.open(req)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def call(self, a, data=None, extra=""):
        st, body = self.raw(a, data, extra)
        try:
            return st, json.loads(body)
        except Exception:
            return st, {"_raw": body[:80]}

    def refresh(self):
        st, j = self.call("me")
        self.csrf = j.get("csrf", "")
        return j


def signup(name, pw):
    c = Client()
    st, j = c.call("signup", {"name": name, "pw": pw})
    return c, st, j


def feed_ids(c, extra=""):
    st, j = c.call("feed", None, extra)
    return [p["id"] for p in j.get("posts", [])], j.get("posts", [])


def tiny_png():
    import struct, zlib
    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"\x00\xff\x00\x00"  # one red pixel
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


def upload_photo(c):
    """Upload one photo to the 'pup' endpoint (multipart) and return its file name."""
    bd = "----mq" + secrets.token_hex(8)
    body = ("--%s\r\nContent-Disposition: form-data; name=\"img\"; filename=\"a.png\"\r\nContent-Type: image/png\r\n\r\n" % bd).encode() + tiny_png() + ("\r\n--%s--\r\n" % bd).encode()
    req = urllib.request.Request(BASE + "?a=pup", body, {"X-CSRF": c.csrf, "Content-Type": "multipart/form-data; boundary=" + bd})
    try:
        return json.loads(c.op.open(req).read()).get("img", "")
    except urllib.error.HTTPError as e:
        return ""


def post_photo(c, a, fields):
    """POST multipart to action a with a one-pixel PNG in the 'avatar' field. Returns (status, json)."""
    bd = "----mq" + secrets.token_hex(8)
    body = b""
    for k, v in fields.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (bd, k, v)).encode()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"avatar\"; filename=\"a.png\"\r\nContent-Type: image/png\r\n\r\n" % bd).encode() + tiny_png() + ("\r\n--%s--\r\n" % bd).encode()
    req = urllib.request.Request(BASE + "?a=" + a, body, {"X-CSRF": c.csrf, "Content-Type": "multipart/form-data; boundary=" + bd})
    try:
        r = c.op.open(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


tag = secrets.token_hex(3)
pw = "correct-horse-1"
na, nb, nc, nd = ("t%s_%s" % (x, tag) for x in "abcd")

print("Recovery codes")
A, st, j = signup(na, pw)
check("sign-up works", st == 200, j)
rc1 = j.get("rc", "")
check("sign-up returns a recovery code", bool(RC_RE.match(rc1)), rc1)
check("me says hasrc", A.refresh()["me"]["hasrc"] == 1)
A.call("logout", {})
A.refresh()
check("wrong password rejected", A.call("login", {"name": na, "pw": "nope-nope-1"})[0] == 401)
check("right password accepted", A.call("login", {"name": na, "pw": pw})[0] == 200)
A.call("logout", {})
A.refresh()
check("wrong recovery code rejected", A.call("recover", {"name": na, "code": "AAAA-BBBB-CCCC-DDDD", "pw": "newpass-123"})[0] == 401)
st, j = A.call("recover", {"name": na, "code": rc1.lower().replace("-", " "), "pw": "newpass-123"})
check("recovery works (case and dashes ignored)", st == 200 and RC_RE.match(j.get("rc", "")), j)
rc2 = j.get("rc", "")
check("recovery issues a different code", rc2 != rc1)
A.call("logout", {})
A.refresh()
check("old code no longer works", A.call("recover", {"name": na, "code": rc1, "pw": "another-123"})[0] == 401)
check("old password no longer works", A.call("login", {"name": na, "pw": pw})[0] == 401)
check("new password works", A.call("login", {"name": na, "pw": "newpass-123"})[0] == 200)
check("new code needs the password", A.call("newrc", {"pw": "wrong-wrong-1"})[0] == 400)
st, j = A.call("newrc", {"pw": "newpass-123"})
check("new code issued", st == 200 and RC_RE.match(j.get("rc", "")), j)

print("Posting")
st, j = A.call("post", {"cap": "hello world", "anon": "1"})
check("post created", st == 200, j)
_, mine = feed_ids(A, "&u=" + na)
pid = mine[0]["id"] if mine else 0
B, st, j = signup(nb, pw)
check("second account created", st == 200, j)
_, seen = feed_ids(B, "&id=%d" % pid)
check("anonymous posting is gone (the anon flag is ignored and the name shows)", seen and seen[0]["name"] == na and not int(seen[0].get("anon", 0)), seen)
check("unmask is refused (nothing is anonymous any more)", A.call("unmask", {"id": pid, "confirm": "1"})[0] == 400)

print("Reports and auto-hide (AUTOHIDE=3, AUTOHIDE_AGE=0)")
check("cannot report own post", A.call("report", {"kind": "post", "id": pid, "why": "x"})[0] == 400)
C, st, _ = signup(nc, pw)
D, st2, _ = signup(nd, pw)
check("more accounts created", st == 200 and st2 == 200)
check("one reporter: still visible", (B.call("report", {"kind": "post", "id": pid, "why": "spam"})[0] == 200) and pid in feed_ids(C, "&id=%d" % pid)[0])
B.call("report", {"kind": "post", "id": pid, "why": "again"})
check("same reporter twice does not count twice", pid in feed_ids(C, "&id=%d" % pid)[0])
C.call("report", {"kind": "post", "id": pid, "why": "spam"})
check("two reporters: still visible", pid in feed_ids(D, "&id=%d" % pid)[0])
D.call("report", {"kind": "post", "id": pid, "why": "spam"})
check("three reporters: hidden from others", pid not in feed_ids(B, "&id=%d" % pid)[0])
check("author still sees it", pid in feed_ids(A, "&id=%d" % pid)[0])
AD = Client()
check("admin logs in", AD.call("login", {"name": ADMIN, "pw": ADMINPW})[0] == 200)
check("admin still sees it", pid in feed_ids(AD, "&id=%d" % pid)[0])
st, j = AD.call("reports")
rep = [r for r in j.get("reports", []) if r["kind"] == "post" and r.get("target") and r["target"]["name"] == na]
check("admin list flags it as auto-hidden", rep and rep[0]["target"].get("hid") == 1, rep[:1])
AD.call("rdone", {"id": rep[0]["id"]}) if rep else None
check("dismiss restores it for everyone", pid in feed_ids(B, "&id=%d" % pid)[0])

print("Suspension")
check("non-admin cannot suspend", B.call("suspend", {"name": nc, "days": "7"})[0] == 403)
check("admin suspends user C", AD.call("suspend", {"name": nc, "days": "7"})[0] == 200)
st, j = C.call("post", {"cap": "should fail"})
check("suspended user cannot post", st == 403, j)
check("suspended user can still read", C.call("feed")[0] == 200)
check("me shows suspension", C.refresh()["me"]["sus"] > 0)
check("admin lifts it", AD.call("suspend", {"name": nc, "days": "0"})[0] == 200)
check("user can post again", C.call("post", {"cap": "back again"})[0] == 200)
check("admins cannot be suspended", AD.call("suspend", {"name": ADMIN, "days": "7"})[0] == 400)

print("Anonymous questions")
check("B asks A a question", B.call("ask", {"to": na, "txt": "What is your favourite colour?"})[0] == 200)
check("cannot ask yourself", A.call("ask", {"to": na, "txt": "me?"})[0] == 400)
check("empty question refused", B.call("ask", {"to": na, "txt": "   "})[0] == 400)
st, j = A.call("asks")
qs = j.get("list", [])
check("owner sees the question", st == 200 and len(qs) == 1 and qs[0]["txt"].startswith("What is"), j)
check("question carries no sender", qs and sorted(qs[0]) == ["id", "ts", "txt"], qs[:1])
check("only the owner has an inbox", B.call("asks")[1].get("list") == [])
st, j = A.call("notifs")
an = [n for n in j.get("list", []) if n["kind"] == "ask"]
check("owner gets an alert that names nobody else", len(an) == 1 and an[0]["name"] == na, j)
check("others cannot answer it", qs and B.call("askans", {"id": qs[0]["id"], "cap": "hi"})[0] == 404)
B.call("askdel", {"id": qs[0]["id"]}) if qs else None
check("others cannot delete it", len(A.call("asks")[1].get("list", [])) == 1)
B.call("ask", {"to": na, "txt": "second question"})
B.call("ask", {"to": na, "txt": "third question"})
check("limit of 3 questions per person per day", B.call("ask", {"to": na, "txt": "fourth question"})[0] == 429)
qs = A.call("asks")[1].get("list", [])
check("three pending, newest first", len(qs) == 3 and qs[0]["txt"].startswith("third"), qs)
q1, q2, q3 = qs[2], qs[1], qs[0]
st, ans = A.call("askans", {"id": q1["id"], "cap": "Green."})
check("owner answers publicly", st == 200 and ans.get("id"), ans)
_, posts = feed_ids(C, "&id=%d" % ans.get("id", 0))
check("answer post shows question, owner and answer", posts and posts[0]["aq"].startswith("What is") and posts[0]["name"] == na and posts[0]["cap"] == "Green.", posts)
check("answered question leaves the inbox", all(x["id"] != q1["id"] for x in A.call("asks")[1].get("list", [])))
st, jn = B.call("notifs")
check("asker is told it was answered", any(n["kind"] == "answer" for n in jn.get("list", [])), jn)
A.call("askdel", {"id": q2["id"]})
check("owner deletes a question", all(x["id"] != q2["id"] for x in A.call("asks")[1].get("list", [])))
check("owner reports a question", A.call("report", {"kind": "ask", "id": q3["id"], "why": "rude"})[0] == 200)
check("reported question leaves the inbox", A.call("asks")[1].get("list") == [])
st, j = AD.call("reports")
rep = [r for r in j.get("reports", []) if r["kind"] == "ask"]
check("admin sees who sent a reported question", rep and rep[0]["target"]["name"] == nb and rep[0]["target"]["cap"].startswith("third"), rep[:1])
AD.call("rdel", {"id": rep[0]["id"]}) if rep else None
check("admin delete clears the report", not [r for r in AD.call("reports")[1].get("reports", []) if r["kind"] == "ask"])
check("owner turns questions off", A.call("profile", {"ask": "0"})[0] == 200)
check("asking is refused while off", B.call("ask", {"to": na, "txt": "anyone there?"})[0] == 403)
A.call("profile", {"ask": "1"})
check("C asks A", C.call("ask", {"to": na, "txt": "from c"})[0] == 200)
check("blocking removes pending questions from that person", A.call("block", {"to": nc})[0] == 200 and A.call("asks")[1].get("list") == [])
check("blocked person cannot ask", C.call("ask", {"to": na, "txt": "again"})[0] == 404)
A.call("unblock", {"to": nc})
check("private account refuses non-friends", D.call("profile", {"priv": "1"})[0] == 200 and B.call("ask", {"to": nd, "txt": "hi"})[0] == 403)

print("Prompt of the day")
st, pj = B.call("prompt")
check("prompt endpoint gives today's question", st == 200 and pj.get("text") and pj.get("day") and pj.get("done") == 0, pj)
st, j = B.call("post", {"cap": "my answer", "pd": "1"})
check("answering the prompt works", st == 200, j)
_, mine = feed_ids(B, "&pd=%d" % pj.get("day", 0))
check("answer is listed under the prompt with its question", mine and mine[0]["aq"] == pj.get("text") and mine[0]["cap"] == "my answer", mine)
check("only one answer per day", B.call("post", {"cap": "again", "pd": "1"})[0] == 400)
check("prompt says answered", B.call("prompt")[1].get("done") == 1)
check("a normal post is not tied to the prompt", B.call("post", {"cap": "plain post"})[0] == 200)
check("prompt answers always show the name (anon flag ignored)", C.call("post", {"cap": "secret", "pd": "1", "anon": "1"})[0] == 200 and all(p["name"] != "" for p in feed_ids(D, "&pd=%d" % pj.get("day", 0))[1] if p["cap"] == "secret"))

print("Masks")
mk = "m%s" % tag
st, j = B.call("maskset", {"name": mk, "bio": "second face"})
check("B creates a mask", st == 200 and j.get("mask", {}).get("name") == mk, j)
check("a username cannot be a mask name", C.call("maskset", {"name": na})[0] == 409)
check("a mask name cannot be reused (any case)", C.call("maskset", {"name": mk.upper()})[0] == 409)
_, st_su, _ = signup(mk, pw)
check("sign-up cannot take a mask name", st_su == 409, st_su)
check("owner's me includes the mask, others' does not", B.refresh()["me"]["mask"]["name"] == mk and A.refresh()["me"].get("mask") is None)
check("post as mask works", B.call("post", {"cap": "from the mask", "as": "mask"})[0] == 200)
_, ps = feed_ids(C, "&k=" + mk)
check("mask page lists it under the mask name", ps and ps[0]["name"] == mk and ps[0]["mk"] == 1 and ps[0]["own"] == 0, ps)
mpid = ps[0]["id"] if ps else 0
check("owner sees it as their own", feed_ids(B, "&k=" + mk)[1][0]["own"] == 1)
_, prof = feed_ids(C, "&u=" + nb)
check("mask posts are not on the real profile", all(p["cap"] != "from the mask" for p in prof), prof)
check("real profile post count excludes mask posts", C.call("user", None, "&u=" + nb)[1]["u"]["posts"] == len(prof))
check("mask comment works", B.call("comment", {"pid": pid, "txt": "hi from mask", "as": "mask"})[0] == 200)
cs = C.call("comments", None, "&pid=%d" % pid)[1].get("comments", [])
check("comment shows the mask name", any(c["txt"] == "hi from mask" and c["name"] == mk for c in cs), cs)
lst = A.call("notifs")[1].get("list", [])
check("alert shows the mask, never the real name", any(n["kind"] == "comment" and n["name"] == mk for n in lst) and all(n["name"] != nb for n in lst), lst)
A.call("notifs")
check("like as the mask is refused without a mask", C.call("like", {"id": pid, "as": "mask"})[0] == 400)
check("like as the mask works", B.call("like", {"id": pid, "as": "mask"})[0] == 200)
lst = A.call("notifs")[1].get("list", [])
check("like alert shows the mask, not the real name", any(n["kind"] == "like" and n["name"] == mk for n in lst) and all(n["name"] != nb for n in lst if n["kind"] == "like"), lst)
B.call("like", {"id": pid})
check("liking as yourself still shows your name", B.call("like", {"id": pid})[0] == 200 and any(n["kind"] == "like" and n["name"] == nb for n in A.call("notifs")[1].get("list", [])))
B.call("like", {"id": pid})
B.call("comment", {"pid": mpid, "txt": "owner reply"})
cs = C.call("comments", None, "&pid=%d" % mpid)[1].get("comments", [])
check("owner's comment on their mask post is shown as the mask", cs and cs[0]["name"] == mk, cs)
check("report a mask", C.call("report", {"kind": "mask", "to": mk, "why": "x"})[0] == 200)
st, j = AD.call("reports")
rep = [r for r in j.get("reports", []) if r["kind"] == "mask"]
check("admin sees the real owner of a reported mask", rep and rep[0]["target"]["name"] == nb, rep[:1])
AD.call("rdone", {"id": rep[0]["id"]}) if rep else None
check("deleting the mask removes its page and posts", B.call("maskdel", {})[0] == 200 and C.call("maskuser", None, "&k=" + mk)[0] == 404 and not feed_ids(C, "&id=%d" % mpid)[0])
check("a deleted mask name stays reserved", C.call("maskset", {"name": mk})[0] == 409)

print("Sensitive photo blur")
im = upload_photo(B)
check("photo upload works", bool(im), im)
st, j = B.call("post", {"cap": "blur me", "imgs": json.dumps([im]), "sens": "1"})
check("post with a sensitive photo", st == 200, j)
_, ps = feed_ids(C, "&u=" + nb)
sp = [p for p in ps if p["cap"] == "blur me"]
check("feed marks it sensitive (1)", sp and int(sp[0]["sens"]) == 1, sp[:1])
spid = sp[0]["id"] if sp else 0
st, j = B.call("post", {"cap": "text only", "sens": "1"})
_, ps = feed_ids(C, "&u=" + nb)
tp = [p for p in ps if p["cap"] == "text only"]
check("sens is ignored on a post without a photo", tp and int(tp[0]["sens"]) == 0, tp[:1])
check("author can turn the blur off", B.call("edit", {"id": spid, "cap": "blur me", "sens": "0"})[1].get("sens") == 0)
check("author can turn the blur on", B.call("edit", {"id": spid, "cap": "blur me", "sens": "1"})[1].get("sens") == 1)
check("edit without sens leaves it alone", B.call("edit", {"id": spid, "cap": "blur me too"})[1].get("sens") == 1)
check("another user can't change it", C.call("edit", {"id": spid, "cap": "x", "sens": "0"})[0] == 404)
check("report the photo post", C.call("report", {"kind": "post", "id": spid, "why": "graphic"})[0] == 200)
st, j = AD.call("reports")
rr = [r for r in j.get("reports", []) if r["kind"] == "post" and r["tid"] == spid]
check("admin sees it has a photo", rr and rr[0]["target"]["himg"] == 1, rr[:1])
check("non-admin can't blur", B.call("rblur", {"id": rr[0]["id"] if rr else 0})[0] == 403)
st, j = AD.call("rblur", {"id": rr[0]["id"] if rr else 0})
check("admin blur sets 2", st == 200 and j.get("sens") == 2, j)
_, ps = feed_ids(C, "&id=%d" % spid)
check("feed shows 2", ps and int(ps[0]["sens"]) == 2, ps[:1])
check("author can't remove an admin's blur", B.call("edit", {"id": spid, "cap": "blur me", "sens": "0"})[1].get("sens") == 2)
st, j = AD.call("rblur", {"id": rr[0]["id"] if rr else 0})
check("admin can remove the blur", st == 200 and j.get("sens") == 0, j)
AD.call("rdone", {"id": rr[0]["id"]}) if rr else None

print("Word filter")
check("non-admin can't edit the list", B.call("bwadd", {"w": "zzhold", "hold": "1"})[0] == 403 and B.call("bwlist")[0] == 403)
check("admin adds a hold word", AD.call("bwadd", {"w": "  ZZHold  Word ", "hold": "1"})[0] == 200)
check("admin adds a flag word", AD.call("bwadd", {"w": "zzflag", "hold": "0"})[0] == 200)
check("too-short word refused", AD.call("bwadd", {"w": "a", "hold": "0"})[0] == 400)
wl = AD.call("bwlist")[1].get("words", [])
check("list is normalised (lowercase, single spaces)", any(w["w"] == "zzhold word" and w["hold"] == 1 for w in wl) and any(w["w"] == "zzflag" and w["hold"] == 0 for w in wl), wl)
st, j = C.call("post", {"cap": "this has ZZHOLD   word in it"})
check("matching post is held", st == 200 and j.get("hold") == 1, j)
_, ps = feed_ids(C, "&u=" + nc)
hp = [p for p in ps if "ZZHOLD" in p["cap"]]
hpid = hp[0]["id"] if hp else 0
check("author still sees it, marked held", hp and int(hp[0]["hold"]) == 1, ps[:2])
check("other users don't see it", hpid not in feed_ids(B, "&id=%d" % hpid)[0] and all("ZZHOLD" not in p["cap"] for p in feed_ids(B, "&u=" + nc)[1]))
check("admin sees it", hpid in feed_ids(AD, "&id=%d" % hpid)[0])
st, j = C.call("post", {"cap": "zzholdwordy is fine, so is zzhold"})
check("whole words only", st == 200 and j.get("hold") == 0, j)
st, j = C.call("post", {"cap": "a zzflag post"})
check("flag word keeps the post visible", st == 200 and j.get("hold") == 0, j)
check("flagged post is visible to others", any("zzflag" in p["cap"] for p in feed_ids(B, "&u=" + nc)[1]))
st, j = AD.call("post", {"cap": "admin says zzhold word"})
check("admins are never filtered", st == 200 and j.get("hold") == 0, j)
st, j = AD.call("reports")
auto = [r for r in j.get("reports", []) if r.get("auto") == 1]
check("filter hits show on the Reports page", any(r["tid"] == hpid and r["kind"] == "post" and r["target"]["held"] == 1 for r in auto), auto[:3])
check("reporter shows as the word filter", all(r["rname"] == "word filter" for r in auto))
check("filter hits don't add to a user's report count", all(r["target"]["n"] == 0 for r in auto if r["target"] and r["target"]["name"] == nc), [r["target"] for r in auto][:3])
rid = [r["id"] for r in auto if r["tid"] == hpid][0] if auto else 0
st, j = B.call("post", {"cap": "plain post for comments"})
_, ps = feed_ids(B, "&u=" + nb)
cpid = [p for p in ps if p["cap"] == "plain post for comments"][0]["id"]
st, j = C.call("comment", {"pid": cpid, "txt": "nasty zzhold word comment"})
check("matching comment is held", st == 200 and j.get("hold") == 1, j)
check("post owner doesn't see a held comment", all("zzhold" not in c["txt"] for c in B.call("comments", None, "&pid=%d" % cpid)[1].get("comments", [])))
check("its author does, marked held", any("zzhold" in c["txt"] and int(c["hold"]) == 1 for c in C.call("comments", None, "&pid=%d" % cpid)[1].get("comments", [])))
check("admin sees it", any("zzhold" in c["txt"] for c in AD.call("comments", None, "&pid=%d" % cpid)[1].get("comments", [])))
check("held comments aren't counted for others", [p for p in feed_ids(B, "&id=%d" % cpid)[1]][0]["cc"] == 0)
st, j = C.call("comment", {"pid": cpid, "txt": "innocent"})
cid = [c["id"] for c in C.call("comments", None, "&pid=%d" % cpid)[1]["comments"] if c["txt"] == "innocent"][0]
st, j = C.call("editc", {"id": cid, "txt": "now zzhold word"})
check("editing a comment into a match holds it", st == 200 and j.get("hold") == 1, j)
st, j = C.call("editc", {"id": cid, "txt": "clean again"})
check("editing it clean releases it", st == 200 and j.get("hold") == 0, j)
st, j = C.call("edit", {"id": hpid, "cap": "now clean"})
check("editing a held post clean releases it", st == 200 and j.get("hold") == 0 and hpid in feed_ids(B, "&id=%d" % hpid)[0], j)
st, j = C.call("post", {"cap": "second zzhold word post"})
_, ps = feed_ids(C, "&u=" + nc)
hp2 = [p for p in ps if "second" in p["cap"]][0]["id"]
st, j = AD.call("reports")
rid2 = [r["id"] for r in j["reports"] if r["tid"] == hp2 and r["kind"] == "post"][0]
check("approving releases the post", AD.call("rdone", {"id": rid2})[0] == 200 and hp2 in feed_ids(B, "&id=%d" % hp2)[0])
st, j = C.call("post", {"cap": "third zzhold word post"})
_, ps = feed_ids(C, "&u=" + nc)
hp3 = [p for p in ps if "third" in p["cap"]][0]["id"]
st, j = AD.call("reports")
rid3 = [r["id"] for r in j["reports"] if r["tid"] == hp3 and r["kind"] == "post"][0]
check("deleting removes a held post", AD.call("rdel", {"id": rid3})[0] == 200 and not feed_ids(AD, "&id=%d" % hp3)[0])
check("admin can remove a word", AD.call("bwdel", {"w": "zzhold word"})[0] == 200 and all(w["w"] != "zzhold word" for w in AD.call("bwlist")[1]["words"]))
AD.call("bwdel", {"w": "zzflag"})
st, j = AD.call("reports")
for r in j.get("reports", []):
    if r.get("auto") == 1:
        AD.call("rdone", {"id": r["id"]})

print("Chat replies, reactions and pins")
HEART, FIRE = "\u2764\ufe0f", "\U0001F525"
A.call("unblock", {"to": nb}); B.call("unblock", {"to": na})
A.call("fadd", {"to": nb}); B.call("facc", {"to": na})
check("A sends a DM", A.call("send", {"to": nb, "txt": "original line"})[0] == 200)
st, j = B.call("thread", None, "&u=" + na)
m1 = j["msgs"][-1]["id"] if st == 200 and j.get("msgs") else 0
check("B sees the DM", m1 > 0, j)
check("B replies to it", B.call("send", {"to": na, "txt": "reply line", "rp": str(m1)})[0] == 200)
st, j = A.call("thread", None, "&u=" + nb)
r2 = [m for m in j.get("msgs", []) if m["txt"] == "reply line"]
check("reply carries a quote of the original", r2 and r2[0]["rq"] and r2[0]["rq"]["id"] == m1 and r2[0]["rq"]["t"] == "original line" and r2[0]["rq"]["mine"] == 1, r2)
check("reply to a message from another chat is refused", B.call("send", {"to": na, "txt": "x", "rp": "999999"})[0] == 400)
check("reactions: B reacts", B.call("react", {"id": str(m1), "e": HEART})[1].get("rx") == [{"e": HEART, "n": 1, "me": 1}])
st, j = A.call("thread", None, "&u=" + nb)
first = [m for m in j["msgs"] if m["id"] == m1][0]
check("A sees B's reaction (me=0)", first["rx"] == [{"e": HEART, "n": 1, "me": 0}], first["rx"])
check("A reacts with a different emoji", len(A.call("react", {"id": str(m1), "e": FIRE})[1].get("rx", [])) == 2)
check("reacting again with the same emoji removes it", len(A.call("react", {"id": str(m1), "e": FIRE})[1].get("rx", [])) == 1)
check("one reaction per person: changing replaces", B.call("react", {"id": str(m1), "e": FIRE})[1].get("rx") == [{"e": FIRE, "n": 1, "me": 1}])
check("unknown emoji refused", B.call("react", {"id": str(m1), "e": "x"})[0] == 400)
check("empty emoji clears", B.call("react", {"id": str(m1), "e": ""})[1].get("rx") == [])
check("outsider cannot react to a DM", C.call("react", {"id": str(m1), "e": HEART})[0] == 404)
check("outsider cannot pin a DM message", C.call("pinm", {"id": str(m1)})[0] == 404)
check("A pins", A.call("pinm", {"id": str(m1)})[1].get("pin", 0) > 0)
st, j = B.call("thread", None, "&u=" + na)
check("B sees the pinned message", [p["id"] for p in j.get("pins", [])] == [m1] and j["pins"][0]["t"] == "original line", j.get("pins"))
check("B unpins it", B.call("pinm", {"id": str(m1)})[1].get("pin") == 0)
check("pins list is empty again", A.call("thread", None, "&u=" + nb)[1].get("pins") == [])
ids = []
for i in range(6):
    A.call("send", {"to": nb, "txt": "pin me %d" % i})
st, j = A.call("thread", None, "&u=" + nb)
ids = [m["id"] for m in j["msgs"] if m["txt"].startswith("pin me")]
res = [A.call("pinm", {"id": str(x)})[0] for x in ids]
check("at most 5 pins per chat", res == [200] * 5 + [400], res)
last = ids[-1]
A.call("react", {"id": str(last), "e": HEART})
A.call("delm", {"id": str(last)})
A.call("send", {"to": nb, "txt": "fresh after delete"})
st, j = A.call("thread", None, "&u=" + nb)
fresh = [m for m in j["msgs"] if m["txt"] == "fresh after delete"][0]
check("deleting a message removes its reactions (no leak to a reused id)", fresh["rx"] == [], fresh)
A.call("send", {"to": nb, "txt": "child", "rp": str(ids[0])})
A.call("delm", {"id": str(ids[0])})
st, j = A.call("thread", None, "&u=" + nb)
child = [m for m in j["msgs"] if m["txt"] == "child"][0]
check("reply to a deleted message shows as unavailable", child["rq"].get("gone") == 1, child["rq"])
# group chat
st, j = A.call("gcreate", {"name": "pins", "members": nb})
g = j.get("id", 0)
check("group created", st == 200 and g > 0, j)
A.call("gsend", {"gid": str(g), "txt": "g one"})
st, j = B.call("gthread", None, "&id=%d" % g)
g1 = j["msgs"][-1]["id"]
check("B replies in the group", B.call("gsend", {"gid": str(g), "txt": "g two", "rp": str(g1)})[0] == 200)
st, j = A.call("gthread", None, "&id=%d" % g)
g2 = [m for m in j["msgs"] if m["txt"] == "g two"][0]
check("group reply carries quote with author name", g2["rq"]["t"] == "g one" and g2["rq"]["mine"] == 1 and g2["rq"]["who"] == na, g2["rq"])
check("reply across groups refused", B.call("gsend", {"gid": str(g), "txt": "x", "rp": "999999"})[0] == 400)
check("group reaction", B.call("greact", {"id": str(g1), "e": HEART})[1].get("rx") == [{"e": HEART, "n": 1, "me": 1}])
check("outsider cannot react in a group", C.call("greact", {"id": str(g1), "e": HEART})[0] == 404)
check("group pin", A.call("gpin", {"id": str(g1)})[1].get("pin", 0) > 0)
st, j = B.call("gthread", None, "&id=%d" % g)
check("group pin visible to others with author name", [p["id"] for p in j["pins"]] == [g1] and j["pins"][0]["who"] == na, j.get("pins"))
check("outsider cannot pin in a group", C.call("gpin", {"id": str(g1)})[0] == 404)
A.call("gleave", {"gid": str(g)}); B.call("gleave", {"gid": str(g)})

print("Group picture")
st, j = A.call("gcreate", {"name": "icons", "members": nb})
g = j.get("id", 0)
check("group has no picture at first", A.call("gthread", None, "&id=%d" % g)[1]["g"]["avatar"] == "")
check("someone outside the group cannot set it", post_photo(C, "gicon", {"gid": g})[0] == 404)
st, j = post_photo(A, "gicon", {"gid": g})
pic = j.get("avatar", "")
check("creator sets the group picture", st == 200 and pic.endswith(".png"), j)
check("members see it in the thread and inbox", B.call("gthread", None, "&id=%d" % g)[1]["g"]["avatar"] == pic and any(x["avatar"] == pic for x in B.call("ginbox")[1]["groups"]))
def img_status(c, f):
    try:
        return c.op.open(BASE + "?img=" + f).status
    except urllib.error.HTTPError as e:
        return e.code
check("a member can load the picture", img_status(B, pic) == 200)
check("a non-member cannot load it", img_status(C, pic) == 404)
check("changing needs a photo or remove flag", A.call("gicon", {"gid": str(g)})[0] == 400)
check("creator removes it", A.call("gicon", {"gid": str(g), "noavatar": "1"})[1].get("avatar") == "")
check("old picture file is gone", img_status(B, pic) == 404)
A.call("gleave", {"gid": str(g)}); B.call("gleave", {"gid": str(g)})

print("Group invite link")
st, j = A.call("gcreate", {"name": "links", "members": nb})
g = j.get("id", 0)
code = A.call("glink", {"gid": str(g)})[1].get("code", "")
check("a member gets an invite link code", len(code) == 16, code)
check("someone outside cannot get the link", C.call("glink", {"gid": str(g)})[0] == 404)
check("link info shows the group", C.call("glinkinfo", None, "&c=" + code)[1].get("g", {}).get("name") == "links")
check("a bad code is refused", C.call("glinkinfo", None, "&c=" + "0" * 16)[0] == 404)
check("opening the link joins the group", C.call("gjoin", {"c": code})[0] == 200 and C.call("gthread", None, "&id=%d" % g)[0] == 200)
check("the join shows as a notice", any(e["kind"] == "join" for e in A.call("gthread", None, "&id=%d" % g)[1]["events"]))
new = A.call("glink", {"gid": str(g), "reset": "1"})[1].get("code", "")
check("resetting makes a new code and the old one stops working", new != code and D.call("gjoin", {"c": code})[0] == 404)
C.call("gleave", {"gid": str(g)}); A.call("gleave", {"gid": str(g)}); B.call("gleave", {"gid": str(g)})

print("Backup")
st, body = AD.raw("backup")
check("admin gets a SQLite file", st == 200 and body.startswith(b"SQLite format 3"), body[:20])
check("non-admin refused", B.raw("backup")[0] == 403)
st, j = AD.call("reports")
check("admin log has entries", len(j.get("log", [])) >= 3, j.get("log"))

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
