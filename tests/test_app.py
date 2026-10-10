"""UI 主链路测试：用 Streamlit 官方 AppTest 真实跑一遍每个页面。

技能坑清单明确要求：不要把无头浏览器当渲染器（Streamlit 是 SPA，
--dump-dom 只能拿到骨架），验证界面必须用 AppTest。
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

import _env  # noqa: F401,E402  —— 隔离测试数据库

from streamlit.testing.v1 import AppTest  # noqa: E402

from core import auth, seed, db  # noqa: E402

APP = str(ROOT / "app.py")

ALL_PAGES = ["dashboard", "learn", "knowledge", "quiz", "my", "news", "forum",
             "files", "live", "store", "profile", "instructor", "admin"]


def _boot() -> None:
    """准备一份可用的演示数据（AppTest 与真实运行使用同一套 seed）。"""
    db.init_db()
    if not seed.is_seeded():
        seed.seed_all()


class AppTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()

    def _run(self, page: str = "dashboard", user: str = "fangyuan"):
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["page"] = page
        at.session_state["theme"] = "light"
        if user:
            u = auth.get_user_by_name(user)
            self.assertIsNotNone(u, f"演示用户 {user} 应存在")
            at.session_state["user"] = dict(u)
        at.run()
        return at

    # ---------------- 未登录：登录页 ----------------
    def test_login_gate_renders(self):
        at = self._run("dashboard", user=None)
        self.assertFalse(at.exception, at.exception)
        text = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("登录", text)

    # ---------------- 每个页面都能无异常渲染 ----------------
    def test_all_pages_render_for_learner(self):
        for page in ALL_PAGES:
            with self.subTest(page=page):
                at = self._run(page, user="fangyuan")
                self.assertFalse(at.exception, f"{page} 渲染异常：{at.exception}")

    def test_all_pages_render_for_admin(self):
        for page in ALL_PAGES:
            with self.subTest(page=page):
                at = self._run(page, user="admin")
                self.assertFalse(at.exception, f"{page}（管理员）渲染异常：{at.exception}")

    def test_all_pages_render_for_instructor(self):
        for page in ["instructor", "learn", "live", "store", "dashboard"]:
            with self.subTest(page=page):
                at = self._run(page, user="liyuan")
                self.assertFalse(at.exception, f"{page}（讲师）渲染异常：{at.exception}")

    # ---------------- 关键交互 ----------------
    def test_knowledge_detail_opens(self):
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["page"] = "knowledge"
        at.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at.session_state["sel_kid"] = 1
        at.run()
        self.assertFalse(at.exception, at.exception)
        text = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("讲解", text)

    def test_news_detail_opens(self):
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["page"] = "news"
        at.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at.session_state["sel_news"] = 1
        at.run()
        self.assertFalse(at.exception, at.exception)

    def test_course_detail_opens(self):
        """已购学员看到学习区，未购学员看到课程大纲（两个分支都要验证）。"""
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["page"] = "learn"
        at.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at.session_state["sel_course"] = 1
        at.run()
        self.assertFalse(at.exception, at.exception)
        text = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("学习区", text)

        at2 = AppTest.from_file(APP, default_timeout=180)
        at2.session_state["page"] = "learn"
        at2.session_state["user"] = dict(auth.get_user_by_name("xiaoai"))
        at2.session_state["sel_course"] = 1
        at2.run()
        self.assertFalse(at2.exception, at2.exception)
        text2 = " ".join(str(m.value) for m in at2.markdown)
        self.assertIn("课程大纲", text2)

    def test_theme_toggle_persists(self):
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["page"] = "dashboard"
        at.session_state["theme"] = "dark"
        at.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at.run()
        self.assertEqual(at.session_state["theme"], "dark")
        self.assertFalse(at.exception, at.exception)

    def test_global_search_renders(self):
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["page"] = "dashboard"
        at.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at.session_state["global_q"] = "大模型"
        at.run()
        self.assertFalse(at.exception, at.exception)
        text = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("搜索", text)

    def test_quiz_practice_flow(self):
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["page"] = "quiz"
        at.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at.run()
        self.assertFalse(at.exception, at.exception)
        # 点击「生成练习」按钮
        start = [b for b in at.button if "生成练习" in str(b.label)]
        self.assertTrue(start, "应存在「生成练习」按钮")
        start[0].click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertIsNotNone(at.session_state.get("quiz_session"))

    def test_query_params_apply_only_on_first_load(self):
        """回归：URL 参数只在首次加载应用，不得覆盖用户点击的导航。

        根因：sync_query_params 会把当前页写回 URL，若每次重跑都读取，
        就会用 URL 旧值覆盖 session_state.page，导致点任何菜单都停在仪表盘。
        """
        # ① 首次加载：URL 深链 ?p=news 应生效
        at = AppTest.from_file(APP, default_timeout=180)
        at.query_params["p"] = "news"
        at.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at.run()
        self.assertEqual(at.session_state["page"], "news")

        # ② 会话内已同步过（qp_applied=True）之后，残留的 ?p=dashboard 不得覆盖导航
        at2 = AppTest.from_file(APP, default_timeout=180)
        at2.query_params["p"] = "dashboard"
        at2.session_state["qp_applied"] = True
        at2.session_state["page"] = "knowledge"
        at2.session_state["user"] = dict(auth.get_user_by_name("fangyuan"))
        at2.run()
        self.assertEqual(at2.session_state["page"], "knowledge")

    def test_login_form_wrong_password(self):
        at = AppTest.from_file(APP, default_timeout=180)
        at.run()
        self.assertFalse(at.exception, at.exception)
        at.text_input[0].set_value("fangyuan")
        at.text_input[1].set_value("000000")
        at.button[0].click().run()
        self.assertFalse(at.exception, at.exception)
        msgs = " ".join(str(e.value) for e in at.error)
        self.assertIn("密码", msgs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
