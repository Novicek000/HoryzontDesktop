"""Spójność sprawdzanej i pobieranej wersji przy aktualizacji z gałęzi."""
import io
import unittest
from unittest.mock import patch

from horyzont.updates import core


class PublicationTest(unittest.TestCase):
    def test_version_and_archive_use_same_commit(self):
        sha = "a" * 40

        def github(url):
            if url.endswith("/commits/main"):
                return {"sha": sha, "commit": {"message": "Horyzont update"}}
            if url.endswith("/HoryzontDesktop"):
                return {"default_branch": "main"}
            return None

        with patch.object(core, "_github", side_effect=github), patch.object(
                core.urllib.request, "urlopen", return_value=io.BytesIO(b'VERSION = "0.4.10"\n')) as request:
            result = core._latest("Novicek000/HoryzontDesktop", "0.4.7")
        self.assertEqual(result[0], "0.4.10")
        self.assertEqual(request.call_args.args[0].full_url,
                         f"https://raw.githubusercontent.com/Novicek000/HoryzontDesktop/{sha}/horyzont/config.py")
        self.assertEqual(result[1], f"https://github.com/Novicek000/HoryzontDesktop/archive/{sha}.tar.gz")

    def test_branch_fallback_when_commit_api_unavailable(self):
        with patch.object(core, "_github", return_value=None), patch.object(
                core.urllib.request, "urlopen", return_value=io.BytesIO(b'VERSION = "0.4.10"\n')):
            result = core._branch_version("Novicek000/HoryzontDesktop")
        self.assertEqual(result["tag_name"], "0.4.10")
        self.assertTrue(result["tarball_url"].endswith("/refs/heads/main.tar.gz"))


if __name__ == "__main__":
    unittest.main()
