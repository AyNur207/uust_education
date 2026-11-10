import io
import tempfile
import unittest
from pathlib import Path

from app import create_app, get_db


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True, "DATABASE": str(Path(self.directory.name)/"test.sqlite3"),
            "UPLOAD_FOLDER": str(Path(self.directory.name)/"uploads"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def token(self, client=None):
        client = client or self.client
        client.get("/")
        with client.session_transaction() as session:
            return session["csrf_token"]

    def post(self, path, data=None, client=None, **kwargs):
        client = client or self.client
        return client.post(path, data={"csrf_token": self.token(client), **(data or {})}, **kwargs)

    def register(self, email="student@example.com", client=None):
        return self.post("/register", {"name":"Студент", "email":email,"password":"test-pass-123", "password_confirm":"test-pass-123","course":"1","group_name":"ТОП-107Б"}, client=client)

    def test_all_public_pages_and_assets(self):
        for path in ["/", "/catalog", "/catalog?page=2", "/register", "/login", "/collections", "/collections/1", "/static/css/style.css", "/static/js/app.js", "/static/fonts/InterVariable.woff2", "/static/img/study-books.png"]:
            with self.subTest(path=path):
                with self.client.get(path) as response:
                    self.assertEqual(response.status_code, 200)
        for material_id in range(1,21):
            self.assertEqual(self.client.get(f"/materials/{material_id}").status_code,200)

    def test_pagination_and_russian_search(self):
        first = self.client.get("/catalog").get_data(as_text=True)
        second = self.client.get("/catalog?page=2").get_data(as_text=True)
        self.assertEqual(first.count('<article class="material-card">'),12)
        self.assertEqual(second.count('<article class="material-card">'),8)
        self.assertIn("Демидович", second)
        self.assertNotIn("Демидович", first)
        self.assertIn("Демидович", self.client.get("/catalog?q=ДЕМИДОВИЧ").get_data(as_text=True))
        self.assertEqual(self.client.get("/catalog?page=-99").status_code,200)
        self.assertIn("Страница 2 из 2",self.client.get("/catalog?page=999").get_data(as_text=True))

    def test_filters_and_sort_survive_pagination(self):
        html = self.client.get("/catalog?subject=Математика&sort=rating").get_data(as_text=True)
        self.assertIn("Найдено 10 материалов",html)
        html = self.client.get("/catalog?kind=Шпаргалка&course=1&semester=1").get_data(as_text=True)
        self.assertIn("Найдено 2 материала",html)
        self.assertIn("Ничего не нашлось",self.client.get("/catalog?q=несуществующийпредмет").get_data(as_text=True))
        self.assertIn("Найдено 0 материалов",self.client.get("/catalog?q=%25").get_data(as_text=True))
        html = self.client.get("/catalog?sort=title").get_data(as_text=True)
        self.assertRegex(html, r'href="/catalog\?sort=title(?:&amp;|&)page=2"')

    def test_register_hash_duplicate_login_and_logout(self):
        self.assertEqual(self.register().status_code,302)
        with self.app.app_context():
            user = get_db().execute("SELECT * FROM users WHERE email='student@example.com'").fetchone()
            self.assertNotEqual(user["password_hash"],"test-pass-123")
            self.assertTrue(user["password_hash"].startswith("scrypt:"))
        self.assertIn("Студент", self.client.get("/profile").get_data(as_text=True))
        self.assertEqual(self.post("/logout").status_code,302)
        self.assertEqual(self.register().status_code,400)
        self.assertEqual(self.post("/login",{"email":"STUDENT@example.com","password":"wrong"}).status_code,400)
        self.assertEqual(self.post("/login?next=//evil.example",{"email":"STUDENT@example.com","password":"test-pass-123"}).location,"/profile")
        self.assertEqual(self.client.get("/profile").status_code,200)

    def test_registration_validation_and_csrf(self):
        response = self.post("/register",{"name":"A","email":"wrong","password":"123","password_confirm":"other","course":"9"})
        self.assertEqual(response.status_code,400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT count(*) FROM users").fetchone()[0],6)
        self.assertEqual(self.client.post("/register",data={}).status_code,400)
        self.assertEqual(self.client.post("/logout",data={"csrf_token":"bad"}).status_code,400)
        self.assertEqual(self.client.post("/logout",data={"csrf_token":"неверный"}).status_code,400)

    def test_favorites_are_per_user_and_persistent(self):
        self.register()
        response = self.post("/materials/1/favorite",headers={"Accept":"application/json"})
        self.assertEqual(response.json,{"saved":True})
        self.assertIn("Массивы и циклы",self.client.get("/profile?tab=favorites").get_data(as_text=True))
        other = self.app.test_client()
        self.register("other@example.com",client=other)
        self.assertNotIn('<article class="material-card">',other.get("/profile?tab=favorites").get_data(as_text=True))
        self.assertEqual(self.post("/materials/1/favorite",headers={"Accept":"application/json"}).json,{"saved":False})

    def upload_data(self, **overrides):
        data = dict(title="Новый материал",description="Описание материала",subject="Математика",course="1",semester="1",kind="Конспект",topic="Пределы",rights="1",source_mode="link",external_url="https://example.com/material")
        return {**data, **overrides}

    def test_link_upload_edit_and_owner_permissions(self):
        self.register()
        response = self.post("/upload",self.upload_data())
        self.assertEqual(response.location,"/materials/21")
        self.assertIn("Новый материал",self.client.get(response.location).get_data(as_text=True))
        self.assertEqual(self.client.get("/materials/21/file").location,"https://example.com/material")
        self.assertEqual(self.post("/materials/21/edit",self.upload_data(title="Исправленный материал")).status_code,302)
        other = self.app.test_client()
        self.register("other@example.com",client=other)
        self.assertEqual(other.get("/materials/21/edit").status_code,403)
        self.assertEqual(self.post("/materials/21/delete",client=other).status_code,403)
        self.assertEqual(self.post("/materials/21/delete").status_code,302)
        self.assertEqual(self.client.get("/materials/21").status_code,404)

    def test_upload_rejects_unsafe_links_missing_rights_and_fake_files(self):
        self.register()
        for overrides in [dict(external_url="javascript:alert(1)"),dict(external_url="https://["),dict(rights=""),dict(course="9"),dict(source_mode="other")]:
            self.assertEqual(self.post("/upload",self.upload_data(**overrides)).status_code,400)
        response = self.post("/upload",self.upload_data(source_mode="file",file=(io.BytesIO(b"not a pdf"),"fake.pdf")),content_type="multipart/form-data")
        self.assertEqual(response.status_code,400)

    def test_file_upload_download_and_replacement(self):
        self.register()
        pdf = b"%PDF-1.4\nexample file for endpoint test\n%%EOF"
        response = self.post("/upload",self.upload_data(source_mode="file",file=(io.BytesIO(pdf),"конспект.pdf")),content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        file_response = self.client.get("/materials/21/file?download=1")
        self.assertEqual(file_response.status_code,200)
        self.assertEqual(file_response.data,pdf)
        self.assertIn("attachment",file_response.headers["Content-Disposition"])
        file_response.close()
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT downloads FROM materials WHERE id=21").fetchone()[0],1)
        self.assertEqual(self.post("/materials/21/edit",self.upload_data(source_mode="file",title="Новое название")).status_code,302)
        old_file = next(Path(self.app.config["UPLOAD_FOLDER"]).iterdir())
        self.assertEqual(self.post("/materials/21/edit",self.upload_data(source_mode="file",file=(io.BytesIO(pdf),"новый.pdf")),content_type="multipart/form-data").status_code,302)
        self.assertFalse(old_file.exists())
        self.assertEqual(len(list(Path(self.app.config["UPLOAD_FOLDER"]).iterdir())),1)
        self.post("/materials/21/delete")
        self.assertEqual(list(Path(self.app.config["UPLOAD_FOLDER"]).iterdir()),[])

    def test_collections_privacy_add_remove_and_reviews(self):
        self.register()
        response = self.post("/collections/create",{"title":"К контрольной","description":"Всё по теме"})
        self.assertEqual(response.location,"/collections/3")
        self.assertEqual(self.post("/collections/3/items/1").status_code,302)
        self.assertIn("Массивы и циклы",self.client.get("/collections/3").get_data(as_text=True))
        guest = self.app.test_client()
        self.assertEqual(guest.get("/collections/3").status_code,403)
        self.assertEqual(self.post("/collections/3/items/1",{"action":"remove"}).status_code,302)
        self.assertEqual(self.post("/materials/1/review",{"rating":"4","body":"Хорошие примеры"}).status_code,302)
        self.post("/materials/1/review",{"rating":"5","body":"Обновлённый отзыв"})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT count(*) FROM reviews WHERE material_id=1").fetchone()[0],3)
            self.assertEqual(get_db().execute("SELECT rating FROM materials WHERE id=1").fetchone()[0],5)
        self.assertEqual(self.post("/materials/1/review",{"rating":"8","body":"Не прошёл"}).status_code,302)

    def test_profile_edit_report_and_xss_escape(self):
        self.register()
        self.post("/profile/edit",{"name":"<script>alert(1)</script>","course":"2","group_name":"ТОП-107Б","bio":"Учусь"})
        html = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("&lt;script&gt;",html)
        self.assertNotIn("<script>alert(1)</script>",html)
        self.post("/materials/1/report",{"reason":"Файл не открывается","body":"Проверьте файл"})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT count(*) FROM reports").fetchone()[0],1)

    def test_access_and_demo_downloads(self):
        for path in ["/profile", "/upload"]:
            self.assertEqual(self.client.get(path).status_code,302)
        self.assertEqual(self.client.get("/collections?mine=1").status_code,302)
        self.assertEqual(self.client.get("/missing").status_code,404)
        self.assertEqual(self.client.get("/materials/999").status_code,404)
        for i in range(1,13):
            response = self.client.get(f"/materials/{i}/file")
            if i == 7: self.assertEqual(response.status_code,302)
            else:
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.data.startswith(b"%PDF-"))
            response.close()
        self.assertEqual(self.client.get("/materials/13/file").status_code,404)


if __name__ == "__main__":
    unittest.main()
