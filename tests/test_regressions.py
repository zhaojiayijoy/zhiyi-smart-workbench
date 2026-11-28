"""Offline regression tests; every test uses a disposable database."""
import copy
import gc
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server as api
from app import auth, db, edu, rehearsal_engine


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        for bucket in api.STORE.values():
            bucket.clear()
        self.password = patch.object(auth, "TEACHER_PASS", "Test-only-password-2026")
        self.password.start()
        self.client = TestClient(api.app)
        self.client.__enter__()
        self.a = db.create_project("Course A")
        self.b = db.create_project("Course B")
        db.import_students(self.a, [{"student_no": "100001", "name": "Alice", "class_name": "A"}])
        db.import_students(self.b, [{"student_no": "200002", "name": "Bob", "class_name": "B"}])
        self.uid = db.create_user(role="student", username="100001", student_no="100001",
                                  display_name="Alice", class_name="A", bound=1,
                                  password_hash=auth.hash_password("Student-test"))
        self.student = {"Authorization": "Bearer " + auth.new_session(self.uid, "student")}
        teacher = db.get_user_by_username(auth.TEACHER_USER)
        self.teacher_id = teacher["id"]
        self.teacher = {"Authorization": "Bearer " + auth.new_session(teacher["id"], "teacher")}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.password.stop()
        db.DB_PATH = self.original_db
        for bucket in api.STORE.values():
            bucket.clear()
        gc.collect()
        self.tmp.cleanup()

    def get(self, path):
        return self.client.get(path, headers=self.student)

    def lesson(self, pid=None):
        return db.save_task(prompt="Lesson", answer="Generated package", kind="lesson",
                            project_id=pid or self.a,
                            meta={"published": True, "pkg": {
                                "title": "Student title", "answer": "ANSWER_CANARY",
                                "ppt": {"slides": [{"notes": "TEACHER_NOTES_CANARY"}]},
                                "lesson_plan": {"steps": [{"phase": "Intro", "minutes": 5,
                                                            "teacher": "Explain", "student": "Discuss"}]}}})

    def review(self, pid=None, no="100001", status="published", **extra):
        meta = {"student_no": no, "student": "Alice", "status": status,
                "ai": {"total": 90, "dimensions": [{"name": "Accuracy", "score": 9, "max": 10}]},
                "teacher": {"scores": {"Accuracy": 0}, "total": 0, "comment": "Released feedback"},
                "final_total": 0}
        meta.update(extra)
        return db.save_task(prompt="Review", kind="review", project_id=pid or self.a, meta=meta)

    def test_auth_required_and_student_cannot_use_teacher_api(self):
        self.assertEqual(self.client.get("/api/student/overview").status_code, 401)
        self.assertEqual(self.get("/api/tasks").status_code, 403)

    def test_profile_class_is_checked_against_roster(self):
        for method, path in (("patch", "/api/auth/me"), ("post", "/api/auth/bind")):
            response = getattr(self.client, method)(path, headers=self.student,
                json={"class_name": "B", "college": "College", "major": "Major"})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(db.get_user(self.uid)["class_name"], "A")
        response = self.client.post("/api/auth/bind", headers=self.student,
            json={"class_name": "A", "college": "College", "major": "Major"})
        self.assertEqual(response.status_code, 200)

    def test_course_access_uses_enrollment_not_profile(self):
        db.update_user(self.uid, class_name="B")
        data = self.get("/api/student/overview").json()["data"]
        self.assertEqual([c["id"] for c in data["courses"]], [self.a])

    def test_foreign_course_rejected_on_every_student_read(self):
        for endpoint in ("overview", "dashboard", "wrong"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.get(f"/api/student/{endpoint}?project_id={self.b}").status_code, 403)
        self.assertEqual(self.client.post("/api/student/ask", headers=self.student,
            json={"project_id": self.b, "question": "Question"}).status_code, 403)

    def test_missing_project_does_not_read_other_courses(self):
        self.lesson(self.b)
        self.review(self.b)
        for endpoint in ("overview", "dashboard"):
            data = self.get(f"/api/student/{endpoint}").json()["data"]
            self.assertEqual(data["my_reviews"], [])
            self.assertEqual(data["lessons"], [])

    def test_no_enrollment_returns_empty_not_global_data(self):
        self.lesson()
        self.review()
        db.clear_students(self.a)
        for endpoint in ("overview", "dashboard"):
            data = self.get(f"/api/student/{endpoint}").json()["data"]
            self.assertEqual(data["my_reviews"], [])
            self.assertEqual(data["lessons"], [])
        self.assertEqual(self.get("/api/student/wrong").json()["data"]["total"], 0)

    def test_editable_name_never_grants_record_access(self):
        own = self.review()
        self.review(no="200002")
        self.review(no="", student="Bob")
        self.client.patch("/api/auth/me", headers=self.student, json={"display_name": "Bob"})
        records = self.get("/api/student/overview").json()["data"]["my_reviews"]
        self.assertEqual([t["id"] for t in records], [own])

    def test_student_payload_hides_answers_notes_and_drafts(self):
        self.lesson()
        self.review(status="submitted", teacher={"comment": "DRAFT_CANARY"})
        self.review(status="published")
        for endpoint in ("overview", "dashboard"):
            response = self.get(f"/api/student/{endpoint}")
            for canary in ("ANSWER_CANARY", "TEACHER_NOTES_CANARY", "DRAFT_CANARY", '"ai"', "password_hash"):
                self.assertNotIn(canary, response.text)
            self.assertIn("Released feedback", response.text)

    def test_teacher_can_still_filter_legacy_records_by_name(self):
        tid = self.review(no="", student="Alice")
        response = self.client.get(f"/api/student/dashboard?project_id={self.a}&student=Alice",
                                   headers=self.teacher)
        self.assertEqual([t["id"] for t in response.json()["data"]["my_reviews"]], [tid])
        response = self.client.get(f"/api/student/wrong?project_id={self.a}&student=Alice",
                                   headers=self.teacher)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get("/api/student/overview").json()["data"]["my_reviews"], [])

    def test_wrong_answers_use_teacher_scores_and_released_reviews(self):
        self.review()
        self.review(status="submitted")
        result = self.get("/api/student/wrong").json()["data"]
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["mastery"], "0%")

    def test_zero_final_score_does_not_fall_back_to_ai(self):
        self.review()
        result = edu.aggregate_analytics(self.a)
        self.assertEqual(result["student_scores"]["Alice"], 0)
        self.assertEqual(result["dimension_avg"]["Accuracy"], 0)
        self.assertIn("Alice", result["need_remedial"])
        self.assertNotIn("Alice", result["can_extend"])

    def test_legacy_submissions_excluded_from_student_ai_context(self):
        db.save_file(name="private.txt", ext="TXT", kind="doc", size=6, content=b"secret",
                     parsed_text="PRIVATE_CANARY", project_id=self.a, visibility="both",
                     category="学生作业", ai_context=1)
        self.assertNotIn("PRIVATE_CANARY", edu.course_context(self.a, student_mode=True))
        self.assertIn("PRIVATE_CANARY", edu.course_context(self.a, student_mode=False))

    def test_submission_upload_is_private_and_keeps_version_history(self):
        tid = self.lesson()
        with patch.object(edu, "extract_text", return_value=("Submission", {"ext": "TXT"})), \
             patch.object(edu, "evaluate_submission", return_value={"total": 90}):
            for version in (1, 2):
                response = self.client.post(f"/api/student/task/{tid}/submit", headers=self.student,
                    files={"file": ("work.txt", b"submission", "text/plain")})
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()["data"]
                self.assertEqual(data["version"], version)
                self.assertIsNone(data["score"])
                f = db.get_file(data["file_id"])
                self.assertEqual(f["visibility"], "teacher")
                self.assertEqual(f["ai_context"], 0)
        versions = self.get(f'/api/student/submissions/{data["submission_id"]}/versions').json()["data"]
        self.assertEqual(len(versions), 2)

    def test_upload_size_limit(self):
        tid = self.lesson()
        with patch.object(edu, "extract_text") as extract:
            response = self.client.post(f"/api/student/task/{tid}/submit", headers=self.student,
                files={"file": ("big.txt", b"x" * (20 * 1024 * 1024 + 1), "text/plain")})
            self.assertFalse(response.json()["ok"])
            extract.assert_not_called()

    def test_demo_never_calls_model_even_with_lesson(self):
        self.lesson()
        with patch.object(rehearsal_engine, "_live_run", side_effect=AssertionError("Model called")) as model:
            response = self.client.post("/api/rehearsals/demo", headers=self.teacher, json={"courseId": self.a})
            self.assertEqual(response.status_code, 200, response.text)
            result = db.get_rehearsal(response.json()["id"])
            self.assertTrue(result["is_demo"])
            self.assertEqual(result["status"], "completed")
            model.assert_not_called()
        self.assertEqual(self.client.post("/api/rehearsals/demo", headers=self.student,
                                         json={"courseId": self.a}).status_code, 403)

    def test_rehearsal_rejects_foreign_lesson(self):
        tid = self.lesson(self.b)
        response = self.client.post("/api/rehearsals", headers=self.teacher,
                                    json={"courseId": self.a, "lessonPackageId": tid})
        self.assertEqual(response.status_code, 400)

    def test_live_rehearsal_uses_structured_package_and_is_not_demo(self):
        tid = self.lesson()
        result = {"events": [], "risks": [], "patches": [], "summary": {"riskCount": 0}}
        with patch.object(rehearsal_engine, "_live_run", return_value=result) as live:
            response = self.client.post("/api/rehearsals", headers=self.teacher,
                                        json={"courseId": self.a, "lessonPackageId": tid})
            session = db.get_rehearsal(response.json()["id"])
            self.assertEqual(session["status"], "completed")
            self.assertFalse(session["is_demo"])
            self.assertEqual(session["timeline"][0]["name"], "Intro")
            live.assert_called_once()

    def test_model_failure_is_labelled_demo(self):
        self.lesson()
        with patch.object(rehearsal_engine, "_live_run", side_effect=RuntimeError("offline")):
            response = self.client.post("/api/rehearsals", headers=self.teacher, json={"courseId": self.a})
            session = db.get_rehearsal(response.json()["id"])
            self.assertTrue(session["is_demo"])

    def test_rehearsal_honors_review_toggle_and_preserves_it_on_rerun(self):
        self.lesson()
        with patch.object(rehearsal_engine, "run_rehearsal") as run:
            response = self.client.post("/api/rehearsals", headers=self.teacher,
                json={"courseId": self.a, "useReviewModel": False})
            self.assertEqual(response.status_code, 200)
            rid = response.json()["id"]
            self.assertFalse(run.call_args.kwargs["use_review_model"])
            self.assertEqual(db.get_rehearsal(rid)["review_model"], "")
            self.client.post(f"/api/rehearsals/{rid}/run", headers=self.teacher)
            self.assertFalse(run.call_args.kwargs["use_review_model"])

    def test_patch_preserves_source_is_idempotent_and_undo_rebuilds_draft(self):
        tid = self.lesson()
        original = copy.deepcopy(db.get_task(tid))
        rid = db.create_rehearsal(course_id=self.a, lesson_package_id=tid, personas=["novice"])
        db.update_rehearsal(rid, patches=[{"patchId": "p1", "status": "pending", "targetArtifact": "ppt",
                                         "targetSection": "Slide 1", "after": "PATCH_CANARY"}])
        url = f"/api/rehearsals/{rid}/patches/p1"
        for _ in range(2):
            response = self.client.post(url + "/apply", headers=self.teacher, json={})
            self.assertEqual(response.status_code, 200, response.text)
        draft_id = response.json()["draft_task_id"]
        draft = db.get_task(draft_id)
        self.assertFalse(draft["meta"]["published"])
        self.assertEqual(len(draft["meta"]["pkg"]["rehearsal_patches"]), 1)
        self.assertEqual(db.get_task(tid), original)
        response = self.client.post(url + "/undo", headers=self.teacher, json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("PATCH_CANARY", json.dumps(db.get_task(draft_id)))
        self.assertEqual(self.client.post(f"/api/rehearsals/{rid}/patches/unknown/apply",
                                         headers=self.teacher, json={}).status_code, 404)
        meta = db.get_task(draft_id)["meta"]
        meta["published"] = True
        db.update_task(draft_id, meta=meta)
        self.assertEqual(self.client.post(url + "/apply", headers=self.teacher, json={}).status_code, 409)
        self.assertEqual(db.get_rehearsal(rid)["patches"][0]["status"], "pending")

    def test_invalid_lesson_plan_does_not_mark_patch_applied(self):
        tid = db.save_task(prompt="Invalid", kind="lesson", project_id=self.a,
                           meta={"pkg": {"lesson_plan": "legacy text"}})
        rid = db.create_rehearsal(course_id=self.a, lesson_package_id=tid, personas=["novice"])
        db.update_rehearsal(rid, patches=[{"patchId": "p1", "status": "pending"}])
        response = self.client.post(f"/api/rehearsals/{rid}/patches/p1/apply",
                                    headers=self.teacher, json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(db.get_rehearsal(rid)["patches"][0]["status"], "pending")

    def test_reset_fresh_database_without_rehearsal_table(self):
        db.reset_all()
        self.assertEqual(db.list_projects(), [])
        self.assertIsNotNone(db.get_user(self.teacher_id))

    def test_reset_removes_rosters_submissions_versions_and_students(self):
        tid = self.lesson()
        db.upsert_submission(project_id=self.a, task_id=tid, student_id=self.uid,
                              student_no="100001", student_name="Alice")
        rehearsal_engine.create_demo_rehearsal(self.a)
        db.reset_all()
        with sqlite3.connect(db.DB_PATH) as conn:
            for table in ("students", "submissions", "submission_versions", "rehearsals", "tasks", "files", "projects"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
        self.assertIsNone(db.get_user(self.uid))
        self.assertEqual(self.get("/api/student/overview").status_code, 401)
        self.assertIsNotNone(db.get_user(self.teacher_id))
        self.assertGreater(db.create_project("After reset"), self.b)

    def test_bootstrap_requires_password_only_for_new_teacher(self):
        with patch.object(auth, "TEACHER_PASS", ""):
            auth.ensure_bootstrap()
            with patch.object(auth, "TEACHER_USER", "new-teacher"):
                with self.assertRaises(RuntimeError):
                    auth.ensure_bootstrap()


if __name__ == "__main__":
    unittest.main()
