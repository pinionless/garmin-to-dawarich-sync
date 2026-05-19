import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask

import utils
from models import db, UserSettings


GPX_BYTES = b'''<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="1" lon="2" /></trkseg></trk></gpx>'''


class DawarichApiUploadTest(unittest.TestCase):
    def make_app(self, tmp_path, api_key="secret-key"):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'test.db'}",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            DAWARICH_HOST="https://dawarich.example.test/",
            DAWARICH_API_KEY=api_key,
            _DAWARICH_CONNECTION_STATUS={"status": None, "timestamp": None, "message": "", "version": None},
        )
        db.init_app(app)
        with app.app_context():
            db.create_all()
            db.session.add(UserSettings(delete_old_gpx=False))
            db.session.commit()
        return app

    def test_submit_location_data_uses_dawarich_import_api_when_api_key_is_configured(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            app = self.make_app(tmp_path)
            gpx_path = tmp_path / "activity.gpx"
            gpx_path.write_bytes(GPX_BYTES)

            response = Mock(ok=True, status_code=201, text='{"id": 42}', json=lambda: {"id": 42})

            with app.app_context(), patch.object(utils, "check_dawarich_connection", return_value=True), patch("utils.requests.post", return_value=response) as post:
                self.assertTrue(utils.submit_location_data(str(gpx_path)))

            post.assert_called_once()
            url = post.call_args.args[0]
            kwargs = post.call_args.kwargs
            self.assertEqual(url, "https://dawarich.example.test/api/v1/imports")
            self.assertEqual(kwargs["params"], {"api_key": "secret-key"})
            self.assertIn("file", kwargs["files"])
            uploaded_file = kwargs["files"]["file"]
            self.assertEqual(uploaded_file[0], "activity.gpx")
            self.assertIn(uploaded_file[2], ("application/gpx+xml", "application/octet-stream"))

    def test_check_dawarich_connection_uses_api_key_without_form_credentials(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            app = self.make_app(tmp_path)
            response = Mock(ok=True, status_code=200, text="[]")
            response.raise_for_status = Mock()

            with app.app_context(), patch("utils.requests.get", return_value=response) as get:
                self.assertTrue(utils.check_dawarich_connection(force_check=True))

            get.assert_called_once_with(
                "https://dawarich.example.test/api/v1/imports",
                params={"api_key": "secret-key", "per_page": 1},
                timeout=10,
            )
            self.assertTrue(app.config["_DAWARICH_CONNECTION_STATUS"]["status"])


if __name__ == "__main__":
    unittest.main()
