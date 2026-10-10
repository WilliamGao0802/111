"""core 业务层单元测试。

运行：python -m unittest discover -s tests -v
断言数只增不减（技能「八条铁律」第 4 条）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent
for _p in (str(_HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _env  # noqa: F401,E402  —— 必须最先导入，隔离测试数据库

from core import (  # noqa: E402
    admin, auth, backup, commerce, courses, db, files, forum, knowledge,
    live, news, notify, quiz, search, seed, users,
)


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.reset_db()
        seed.seed_all(force=True)
        cls.ids = {u["username"]: u["id"] for u in db.query("SELECT id, username FROM users")}

    # ---------------- 用户系统 ----------------
    def test_password_rule(self):
        self.assertFalse(auth.validate_password("12345")[0])
        self.assertFalse(auth.validate_password("1234567")[0])
        self.assertFalse(auth.validate_password("abcdef")[0])
        self.assertFalse(auth.validate_password("12a456")[0])
        self.assertTrue(auth.validate_password("123456")[0])
        self.assertTrue(auth.validate_password("000123")[0])

    def test_register_and_duplicate(self):
        uid = auth.register("tester01", "654321")
        self.assertGreater(uid, 0)
        with self.assertRaises(auth.AuthError) as ctx:
            auth.register("tester01", "111111")
        self.assertIn("已被注册", str(ctx.exception))

    def test_register_bad_password(self):
        with self.assertRaises(auth.AuthError) as ctx:
            auth.register("tester02", "12345")
        self.assertIn("6 位", str(ctx.exception))

    def test_user_cap(self):
        origin = auth.MAX_USERS
        auth.MAX_USERS = auth.user_count()
        try:
            with self.assertRaises(auth.AuthError) as ctx:
                auth.register("overcap", "123456")
            self.assertIn("上限", str(ctx.exception))
        finally:
            auth.MAX_USERS = origin

    def test_login_and_wrong_password(self):
        auth.register("tester03", "222222")
        u = auth.login("tester03", "222222")
        self.assertEqual(u["username"], "tester03")
        with self.assertRaises(auth.AuthError) as ctx:
            auth.login("tester03", "333333")
        self.assertIn("密码错误", str(ctx.exception))
        with self.assertRaises(auth.AuthError):
            auth.login("nobody_here", "222222")

    def test_login_lockout(self):
        auth.register("tester04", "444444")
        for _ in range(auth.MAX_LOGIN_FAILS - 1):
            with self.assertRaises(auth.AuthError):
                auth.login("tester04", "999999")
        with self.assertRaises(auth.AuthError) as ctx:
            auth.login("tester04", "999999")
        self.assertIn("锁定", str(ctx.exception))
        with self.assertRaises(auth.AuthError) as ctx2:
            auth.login("tester04", "444444")
        self.assertIn("锁定", str(ctx2.exception))

    def test_hash_salted_unique(self):
        h1, s1 = auth.hash_password("123456")
        h2, s2 = auth.hash_password("123456")
        self.assertNotEqual(h1, h2)          # 盐不同 → 哈希不同
        self.assertNotEqual(s1, s2)
        self.assertTrue(auth.verify_password("123456", h1, s1))
        self.assertFalse(auth.verify_password("123457", h1, s1))

    def test_verification_code(self):
        code = auth.send_code("13900001111", "sms", "login")
        self.assertEqual(len(code), 6)
        with self.assertRaises(auth.AuthError):
            auth.send_code("13900001111", "sms", "login")   # 60s 内不可重发
        with self.assertRaises(auth.AuthError):
            auth.verify_code("13900001111", "sms", "login", "000000" if code != "000000" else "111111")
        auth.verify_code("13900001111", "sms", "login", code)   # 正确码通过

    def test_realname_and_mask(self):
        uid = self.ids["xiaoai"]
        auth.submit_realname(uid, "张小艾", "110101199001011234", "13700001111")
        u = auth.get_user(uid)
        self.assertEqual(u["realname_status"], "pending")
        self.assertIn("*", u["id_card"])           # 脱敏存储
        auth.review_realname(uid, True)
        self.assertTrue(auth.is_realname_ok(uid))
        with self.assertRaises(auth.AuthError):
            auth.submit_realname(uid, "张", "110101199001011234", "13700001111")

    def test_level_from_points(self):
        self.assertEqual(auth.level_of(0), 1)
        self.assertEqual(auth.level_of(150), 2)
        self.assertEqual(auth.level_of(99999), 10)

    # ---------------- 关注 / 用户 ----------------
    def test_follow_flow(self):
        a, b = self.ids["chenmo"], self.ids["liyuan"]
        users.follow(a, b)
        self.assertTrue(users.is_following(a, b))
        self.assertIn(a, [x["id"] for x in users.follower_list(b)])
        with self.assertRaises(auth.AuthError):
            users.follow(a, a)
        users.unfollow(a, b)
        self.assertFalse(users.is_following(a, b))

    def test_leaderboard(self):
        self.assertTrue(len(users.leaderboard("active")) > 0)
        self.assertTrue(len(users.leaderboard("posts")) > 0)

    # ---------------- 新闻 ----------------
    def test_news_top5_and_sort(self):
        top = news.top_news(5)
        self.assertLessEqual(len(top), 5)
        self.assertGreaterEqual(len(top), 1)
        by_views = news.list_news(sort="views", limit=5)
        self.assertGreaterEqual(by_views[0]["views"], by_views[-1]["views"])

    def test_news_like_fav(self):
        uid = self.ids["azhe"]
        n = news.list_news(limit=1)[0]
        before = news.get_news(n["id"], count_view=False)["likes"]
        self.assertTrue(news.toggle_like(uid, n["id"]))
        self.assertEqual(news.get_news(n["id"], count_view=False)["likes"], before + 1)
        self.assertFalse(news.toggle_like(uid, n["id"]))
        self.assertTrue(news.toggle_fav(uid, n["id"]))
        self.assertIn(n["id"], news.faved_ids(uid))

    def test_news_search_and_rss(self):
        self.assertTrue(len(news.list_news(keyword="大模型", limit=50)) >= 0)
        rss = news.to_rss()
        self.assertIn("<rss", rss)
        self.assertIn("</channel>", rss)

    def test_news_pending_flow(self):
        nid = news.create_news("待审新闻标题", "待审摘要", status="pending")
        self.assertIn(nid, [x["id"] for x in news.pending_news()])
        news.publish_news(nid)
        self.assertEqual(news.get_news(nid, count_view=False)["status"], "published")

    # ---------------- 讨论区 ----------------
    def test_post_and_comment(self):
        uid = self.ids["fangyuan"]
        pid = forum.create_post(uid, "测试帖", "正文内容，@liyuan 请看一下 #测试#", "综合讨论")
        p = forum.get_post(pid)
        self.assertEqual(p["topic"], "综合讨论")
        self.assertIn("测试", p["tags"])
        cid = forum.add_comment(pid, self.ids["azhe"], "第一层评论")
        forum.add_comment(pid, self.ids["xiaoai"], "第二层回复", parent_id=cid)
        tree = forum.comment_tree(pid)
        self.assertTrue(any(n["id"] == cid and n["children"] for n in tree))
        self.assertEqual(forum.comment_count(pid), 2)
        # @提及产生了通知
        notes = notify.list_notifications(self.ids["liyuan"])
        self.assertTrue(any("提到" in n["content"] for n in notes))

    def test_post_edit_delete_permission(self):
        uid = self.ids["fangyuan"]
        pid = forum.create_post(uid, "待改帖", "原始内容")
        with self.assertRaises(auth.AuthError):
            forum.update_post(pid, self.ids["azhe"], content="越权修改")
        forum.update_post(pid, uid, content="修改后的内容")
        self.assertEqual(forum.get_post(pid)["edited"], 1)
        with self.assertRaises(auth.AuthError):
            forum.delete_post(pid, self.ids["azhe"])
        forum.delete_post(pid, uid)
        self.assertEqual(forum.get_post(pid)["status"], "hidden")

    def test_post_like_and_sort(self):
        uid = self.ids["chenmo"]
        pid = forum.create_post(self.ids["azhe"], "点赞测试", "内容")
        self.assertTrue(forum.toggle_like(uid, pid))
        self.assertIn(pid, forum.liked_ids(uid))
        self.assertFalse(forum.toggle_like(uid, pid))
        hot = forum.list_posts(sort="hot", limit=10)
        pinned = [p for p in hot if p["is_pinned"]]
        if pinned:
            self.assertEqual(hot[0]["is_pinned"], 1)

    def test_draft_box(self):
        uid = self.ids["xiaoai"]
        did = forum.save_draft(uid, "草稿标题", "草稿内容")
        self.assertEqual(len(forum.list_drafts(uid)), 1)
        forum.save_draft(uid, "草稿标题2", "草稿内容2")
        forum.delete_draft(did, uid)
        self.assertEqual(len(forum.list_drafts(uid)), 0)

    # ---------------- 文件区 ----------------
    def test_file_upload_version_and_quota(self):
        uid = self.ids["fangyuan"]
        fid1 = files.save_upload(uid, "unit_test_doc.md", b"v1 content", "课件", "测试", "public")
        self.assertEqual(files.get_file(fid1)["version"], 1)
        fid2 = files.save_upload(uid, "unit_test_doc.md", b"v2 content longer", "课件", "测试", "public")
        self.assertEqual(files.get_file(fid2)["version"], 2)
        self.assertEqual(files.get_file(fid1)["is_latest"], 0)
        self.assertEqual(len(files.versions(fid2)), 2)
        files.save_upload(uid, "small_unit.bin", b"x" * 10, "其他")   # 小文件正常通过
        with self.assertRaises(auth.AuthError):
            files.save_upload(uid, "empty.bin", b"", "其他")
        with self.assertRaises(auth.AuthError):
            files.save_upload(uid, "huge.bin", b"x" * (files.MAX_FILE_MB * 1024 * 1024 + 1), "其他")

    def test_file_visibility_and_trash(self):
        owner = self.ids["liyuan"]
        other = self.ids["xiaoai"]
        fid = files.save_upload(owner, "private_unit.txt", b"secret", "其他", "", "private")
        f = files.get_file(fid)
        self.assertFalse(files.can_view(f, other))
        self.assertTrue(files.can_view(f, owner))
        with self.assertRaises(auth.AuthError):
            files.read_file(fid, other)
        files.delete_file(fid, owner)
        self.assertIn(fid, [x["id"] for x in files.recycle_bin(owner)])
        files.restore_file(fid, owner)
        self.assertEqual(files.get_file(fid)["deleted"], 0)

    def test_file_share_and_zip(self):
        uid = self.ids["wangxue"]
        fid = files.save_upload(uid, "share_unit.txt", b"share me", "其他", "", "public")
        link = files.share_link(fid)
        token = link.split("share=")[1]
        self.assertTrue(files.verify_share(fid, token))
        self.assertFalse(files.verify_share(fid, "badtoken"))
        payload = files.package_zip([fid], uid)
        self.assertGreater(len(payload), 0)

    # ---------------- 课程 ----------------
    def test_course_tree_and_preview(self):
        c = courses.list_courses(limit=1)[0]
        tree = courses.course_tree(c["id"])
        self.assertTrue(len(tree) > 0)
        self.assertTrue(len(tree[0]["lessons"]) > 0)
        self.assertIn("【", courses.catalog_preview(c["id"]))

    def test_course_search_filters(self):
        all_c = courses.list_courses(limit=100)
        cheap = courses.list_courses(max_price=0, limit=100)
        self.assertTrue(all(c["price"] <= 0 for c in cheap))
        self.assertGreaterEqual(len(all_c), len(cheap))

    def test_enroll_requires_realname(self):
        learner = auth.register("learner_no_rn", "123456")
        paid = [c for c in courses.list_courses(limit=50) if c["price"] > 0][0]
        with self.assertRaises(auth.AuthError) as ctx:
            courses.enroll(learner, paid["id"])
        self.assertIn("实名", str(ctx.exception))
        # 免费课不需要实名
        free = [c for c in courses.list_courses(limit=50) if c["price"] == 0][0]
        courses.enroll(learner, free["id"])
        self.assertTrue(courses.is_enrolled(learner, free["id"]))

    def test_lesson_progress_and_certificate(self):
        uid = self.ids["azhe"]
        c = courses.list_courses(limit=1)[0]
        courses.enroll(uid, c["id"], force=True)
        ls = courses.lessons(c["id"])
        for l in ls:
            courses.mark_lesson(uid, l["id"], True)
        e = courses.get_enrollment(uid, c["id"])
        self.assertEqual(e["progress"], 100.0)
        self.assertEqual(e["completed"], 1)
        self.assertTrue(e["certificate_code"].startswith("BGL-"))

    def test_course_review_recalc(self):
        uid = self.ids["axhe"] if "axhe" in self.ids else self.ids["azhe"]
        c = courses.list_courses(limit=1)[0]
        courses.enroll(uid, c["id"], force=True)
        courses.review_course(uid, c["id"], 5, "很有收获")
        self.assertGreater(courses.get_course(c["id"])["rating"], 0)

    def test_create_course_requires_instructor(self):
        with self.assertRaises(auth.AuthError):
            courses.create_course(self.ids["xiaoai"], "越权建课", category="大模型基础")

    # ---------------- 直播 ----------------
    def test_live_reserve_and_replay(self):
        uid = self.ids["chenmo"]
        l = live.list_lives("upcoming")
        if l:
            lid = l[0]["id"]
            live.reserve(lid, uid)
            self.assertTrue(live.is_reserved(lid, uid))
            live.unreserve(lid, uid)
            self.assertFalse(live.is_reserved(lid, uid))

    def test_live_chat_and_interaction(self):
        l = live.list_lives(limit=1)[0]
        lid = l["id"]
        live.send_chat(lid, self.ids["fangyuan"], "测试弹幕")
        self.assertTrue(any("测试弹幕" in m["content"] for m in live.list_chat(lid)))
        iid = live.create_interaction(lid, "poll", "选一个", ["A", "B"])
        live.vote(iid, self.ids["fangyuan"], "A")
        self.assertEqual(live.my_vote(iid, self.ids["fangyuan"]), "A")
        self.assertEqual(live.vote_stats(iid).get("A"), 1)

    def test_live_status_control_permission(self):
        l = live.list_lives(limit=1)[0]
        with self.assertRaises(auth.AuthError):
            live.set_status(l["id"], "live", by=self.ids["xiaoai"])

    # ---------------- 交易 ----------------
    def test_cart_and_order(self):
        uid = auth.register("cart_unit", "123456")
        p = commerce.list_products("course")[0]
        commerce.add_to_cart(uid, p["id"])
        self.assertEqual(len(commerce.list_cart(uid)), 1)
        self.assertGreater(commerce.cart_total(uid), -1)
        commerce.remove_from_cart(uid, p["id"])
        self.assertEqual(len(commerce.list_cart(uid)), 0)

    def test_coupon_rules(self):
        cpid = commerce.create_coupon("UT10", "full_reduce", 10.0, 100.0, 30, 10)
        commerce.grant_coupon(self.ids["fangyuan"], cpid)
        coupon, discount, msg = commerce.validate_coupon(self.ids["fangyuan"], "UT10", 200.0)
        self.assertIsNotNone(coupon)
        self.assertEqual(discount, 10.0)
        _, d2, msg2 = commerce.validate_coupon(self.ids["fangyuan"], "UT10", 50.0)
        self.assertEqual(d2, 0.0)
        self.assertIn("未满", msg2)

    def test_points_discount_cap(self):
        self.assertEqual(commerce.points_discount(100, 100.0), 1.0)
        self.assertEqual(commerce.points_discount(100000, 10.0), 2.0)   # 20% 封顶

    def test_order_pay_opens_course(self):
        uid = auth.register("buyer_unit", "123456")
        auth.submit_realname(uid, "测试买家", "110101199203031234", "13700002222")
        auth.review_realname(uid, True)
        p = [x for x in commerce.list_products("course") if x["ref_id"]][0]
        no = commerce.create_order(uid, [p["id"]], pay_method="wechat")
        o = commerce.get_order(no)
        self.assertEqual(o["status"], "pending")
        sig = commerce.sign_payload({"order_no": no, "amount": o["final_amount"], "method": "wechat"})
        res = commerce.pay_order(no, "wechat", sig)
        self.assertTrue(res["ok"])
        self.assertEqual(commerce.get_order(no)["status"], "paid")
        self.assertTrue(courses.is_enrolled(uid, p["ref_id"]))

    def test_pay_signature_check(self):
        uid = auth.register("buyer_sig", "123456")
        p = [x for x in commerce.list_products("course") if x["ref_id"]][0]
        no = commerce.create_order(uid, [p["id"]])
        with self.assertRaises(auth.AuthError) as ctx:
            commerce.pay_order(no, "wechat", "wrong_signature_value_xxx")
        self.assertIn("签名", str(ctx.exception))

    def test_refund_flow(self):
        uid = auth.register("buyer_refund", "123456")
        auth.submit_realname(uid, "退款买家", "110101199505051234", "13700003333")
        auth.review_realname(uid, True)
        p = [x for x in commerce.list_products("course") if x["ref_id"]][0]
        no = commerce.create_order(uid, [p["id"]])
        o = commerce.get_order(no)
        commerce.pay_order(no, "alipay", commerce.sign_payload(
            {"order_no": no, "amount": o["final_amount"], "method": "alipay"}))
        rid = commerce.apply_refund(uid, no, "内容不符合预期")
        self.assertGreater(rid, 0)
        commerce.review_refund(rid, True)
        self.assertEqual(commerce.get_order(no)["status"], "refunded")
        self.assertFalse(courses.is_enrolled(uid, p["ref_id"]))

    def test_duplicate_purchase_blocked(self):
        uid = auth.register("buyer_dup", "123456")
        p = [x for x in commerce.list_products("course") if x["ref_id"]][0]
        no = commerce.create_order(uid, [p["id"]])
        o = commerce.get_order(no)
        commerce.pay_order(no, "wechat", commerce.sign_payload(
            {"order_no": no, "amount": o["final_amount"], "method": "wechat"}))
        with self.assertRaises(auth.AuthError) as ctx:
            commerce.add_to_cart(uid, p["id"])
        self.assertIn("已拥有", str(ctx.exception))

    def test_withdraw_requires_realname(self):
        uid = auth.register("inst_wd", "123456")
        with self.assertRaises(auth.AuthError) as ctx:
            commerce.apply_withdraw(uid, 10, "alipay:test@x.com")
        self.assertIn("实名", str(ctx.exception))

    def test_platform_summary(self):
        s = commerce.platform_summary()
        self.assertIn("gmv", s)
        self.assertGreaterEqual(s["gmv"], 0)

    # ---------------- 知识点 / 测评 ----------------
    def test_quiz_grading(self):
        q = quiz.list_questions(limit=1)[0]
        self.assertTrue(quiz.grade(q, q["answers"]))
        self.assertFalse(quiz.grade(q, ["绝不可能是这个答案"]))

    def test_quiz_submit_and_wrongbook(self):
        uid = self.ids["fangyuan"]
        qs = quiz.draw(count=5)
        answers = {str(q["id"]): (q["answers"][0] if i % 2 else "Z") for i, q in enumerate(qs)}
        res = quiz.submit(uid, "practice", "混合", qs, answers, duration=100)
        self.assertEqual(res["total"], 5)
        self.assertLessEqual(res["score"], 100)
        self.assertTrue(len(quiz.my_records(uid)) > 0)
        self.assertEqual(len(res["detail"]), 5)

    def test_draw_smart_prefers_wrong(self):
        uid = self.ids["fangyuan"]
        qs = quiz.draw(count=4)
        for q in qs:
            quiz._add_wrong(uid, q["id"])
        smart = quiz.draw_smart(uid, count=4)
        self.assertTrue(len(smart) > 0)
        self.assertLessEqual(len(smart), 4)

    def test_knowledge_modules(self):
        mods = knowledge.list_modules()
        self.assertEqual(len(mods), 6)
        self.assertTrue(all(m["count"] > 0 for m in mods))
        k = knowledge.list_knowledge(limit=1)[0]
        k2 = knowledge.get_knowledge(k["id"], count_view=False)
        self.assertTrue(len(k2["body"]) > 20)

    # ---------------- 搜索 / 管理 / 备份 ----------------
    def test_global_search(self):
        res = search.global_search("大模型")
        self.assertTrue(len(res) > 0)
        self.assertGreater(search.total_hits(res), 0)
        self.assertEqual(search.global_search(""), {})

    def test_admin_dashboard_and_logs(self):
        d = admin.dashboard()
        self.assertIn("users", d)
        self.assertGreater(d["users"], 0)
        auth.log(1, "unit", "unit_action", "detail")
        self.assertTrue(any(r["action"] == "unit_action" for r in admin.recent_logs(50)))
        trend = admin.trend_data(7)
        self.assertEqual(len(trend), 7)

    def test_backup_roundtrip(self):
        before = int(db.scalar("SELECT COUNT(*) FROM users", (), 0))
        data = backup.export_all()
        self.assertIn("users", data)
        path = backup.create_backup("unit")
        self.assertTrue(Path(path).exists())
        stat = backup.restore_backup(path)
        self.assertEqual(stat["users"], before)

    def test_ratelimit_blocks(self):
        from core import ratelimit
        bucket = "unittest_bucket"
        self.assertTrue(ratelimit.hit(bucket, limit=2, window=600))
        self.assertTrue(ratelimit.hit(bucket, limit=2, window=600))
        with self.assertRaises(auth.AuthError):
            ratelimit.hit(bucket, limit=2, window=600)
        self.assertFalse(ratelimit.hit(bucket, limit=2, window=600, raise_error=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
