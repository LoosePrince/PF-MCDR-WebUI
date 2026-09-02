import asyncio
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from guguwebui.services.mod_service import ModService
from guguwebui.structures import BusinessException


class FakeConfig:
    def __init__(self, working_directory: str, start_command: str = "java -jar fabric-server-launch.jar"):
        self.working_directory = working_directory
        self.start_command = start_command


class FakeServer:
    def __init__(self, working_directory: str, *, running: bool = False, start_command: str = "java -jar fabric-server-launch.jar"):
        self.config = FakeConfig(working_directory, start_command)
        self.running = running

    def get_mcdr_config(self):
        return self.config

    def is_server_running(self):
        return self.running

    def is_server_startup(self):
        return False


class FakeUpload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self.stream = io.BytesIO(data)
        self.closed = False

    async def read(self, size: int):
        return self.stream.read(size)

    async def close(self):
        self.closed = True


def jar_bytes(entries: dict[str, str | bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as jar:
        for name, value in entries.items():
            jar.writestr(name, value)
    return stream.getvalue()


def fabric_meta(mod_id: str, *, depends=None, breaks=None, icon=None) -> str:
    data = {
        "schemaVersion": 1,
        "id": mod_id,
        "name": mod_id.title(),
        "version": "1.0.0",
        "authors": ["Tester"],
        "description": f"{mod_id} description",
        "environment": "server",
    }
    if depends is not None:
        data["depends"] = depends
    if breaks is not None:
        data["breaks"] = breaks
    if icon is not None:
        data["icon"] = icon
    return json.dumps(data)


class ModServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.server = FakeServer(str(self.root))
        self.service = ModService(self.server)
        self.mods = self.root / "mods"
        self.mods.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_jar(self, name: str, entries: dict[str, str | bytes]):
        path = self.mods / name
        path.write_bytes(jar_bytes(entries))
        return path

    def assert_business_error(self, status_code: int, callback):
        with self.assertRaises(BusinessException) as caught:
            callback()
        self.assertEqual(caught.exception.status_code, status_code)
        return caught.exception

    def test_recognizes_all_supported_loaders_and_unknown_jar(self):
        self.write_jar("fabric.jar", {"fabric.mod.json": fabric_meta("fabric_mod")})
        self.write_jar("quilt.jar", {"quilt.mod.json": json.dumps({
            "quilt_loader": {"id": "quilt_mod", "version": "2", "metadata": {"name": "Quilt Mod"}}
        })})
        self.write_jar("forge.jar", {"META-INF/mods.toml": '''
modLoader="javafml"
loaderVersion="[47,)"
[[mods]]
modId="forge_mod"
version="3"
displayName="Forge Mod"
[[dependencies.forge_mod]]
modId="minecraft"
mandatory=true
versionRange="[1.20.1,)"
'''})
        self.write_jar("neo.jar", {"META-INF/neoforge.mods.toml": '''
modLoader="javafml"
loaderVersion="[2,)"
[[mods]]
modId="neo_mod"
version="4"
displayName="Neo Mod"
[[dependencies.neo_mod]]
modId="bad_mod"
type="incompatible"
versionRange="*"
'''})
        self.write_jar("unknown.jar", {"META-INF/MANIFEST.MF": "Implementation-Title: Unknown\nImplementation-Version: 5\n"})

        mods = {item["filename"]: item for item in self.service.list_mods()["mods"]}
        self.assertEqual(mods["fabric.jar"]["loader"], "fabric")
        self.assertEqual(mods["quilt.jar"]["id"], "quilt_mod")
        self.assertEqual(mods["forge.jar"]["dependencies"][0]["version"], "[1.20.1,)")
        self.assertEqual(mods["neo.jar"]["conflicts"][0]["id"], "bad_mod")
        self.assertFalse(mods["unknown.jar"]["recognized"])
        self.assertIn("unknown_metadata", {warning["code"] for warning in mods["unknown.jar"]["warnings"]})

    def test_invalid_jar_and_limited_icon_are_safe(self):
        (self.mods / "broken.jar").write_bytes(b"not a zip")
        png = b"\x89PNG\r\n\x1a\n" + b"payload"
        self.write_jar("icon.jar", {
            "fabric.mod.json": fabric_meta("icon_mod", icon={"16": "small.png", "128": "large.png"}),
            "large.png": png,
            "small.png": png,
        })
        mods = {item["filename"]: item for item in self.service.list_mods()["mods"]}
        self.assertIn("invalid_jar", {warning["code"] for warning in mods["broken.jar"]["warnings"]})
        data, media_type = self.service.get_icon("icon.jar")
        self.assertEqual(data, png)
        self.assertEqual(media_type, "image/png")

    def test_loader_missing_dependency_duplicate_and_conflict_warnings(self):
        self.write_jar("a.jar", {"fabric.mod.json": fabric_meta("same", depends={"missing": ">=1"})})
        self.write_jar("b.jar", {"fabric.mod.json": fabric_meta("same")})
        self.write_jar("forge.jar", {"META-INF/mods.toml": 'modLoader="javafml"\n[[mods]]\nmodId="forge_mod"\nversion="1"\n'})
        self.write_jar("conflict.jar", {"fabric.mod.json": fabric_meta("conflict", breaks={"same": "*"})})
        mods = self.service.list_mods()["mods"]
        codes = {item["filename"]: {warning["code"] for warning in item["warnings"]} for item in mods}
        self.assertIn("duplicate_id", codes["a.jar"])
        self.assertIn("missing_dependency", codes["a.jar"])
        self.assertIn("declared_conflict", codes["conflict.jar"])
        self.assertIn("loader_mismatch", codes["forge.jar"])

    def test_toggle_requires_warning_acknowledgement_and_never_overwrites(self):
        self.write_jar("base.jar", {"fabric.mod.json": fabric_meta("base")})
        self.write_jar("dependent.jar", {"fabric.mod.json": fabric_meta("dependent", depends={"base": "*"})})
        error = self.assert_business_error(
            409, lambda: self.service.toggle("base.jar", False)
        )
        self.assertIn("reverse_dependency", {item["code"] for item in error.data["warnings"]})
        result = self.service.toggle("base.jar", False, True)
        self.assertEqual(result["filename"], "base.jar.disabled")
        self.assertTrue((self.mods / "base.jar.disabled").is_file())

        self.write_jar("collision.jar", {"fabric.mod.json": fabric_meta("collision")})
        self.write_jar("collision.jar.disabled", {"fabric.mod.json": fabric_meta("collision")})
        self.assert_business_error(409, lambda: self.service.toggle("collision.jar", False, True))

    def test_toggle_reports_locked_file(self):
        self.write_jar("locked.jar", {"fabric.mod.json": fabric_meta("locked")})
        with patch.object(ModService, "_rename_no_replace", side_effect=PermissionError(13, "locked")):
            error = self.assert_business_error(423, lambda: self.service.toggle("locked.jar", False, True))
        self.assertIn("占用", error.message)

    def test_restart_state_only_tracks_changes_to_enabled_mods(self):
        self.server.running = True
        disabled = self.write_jar("disabled.jar.disabled", {"fabric.mod.json": fabric_meta("disabled")})
        trash = self.service.trash(disabled.name)
        self.assertFalse(trash["needs_restart"])
        restored = self.service.restore(trash["trash_id"])
        self.assertFalse(restored["needs_restart"])
        enabled = self.write_jar("enabled.jar", {"fabric.mod.json": fabric_meta("enabled")})
        self.assertTrue(self.service.trash(enabled.name)["needs_restart"])

    def test_upload_limits_validation_conflicts_and_cleanup(self):
        valid = jar_bytes({"fabric.mod.json": fabric_meta("uploaded")})
        too_large = FakeUpload("large.jar", valid)
        self.assert_business_error(
            413, lambda: asyncio.run(self.service.upload(too_large, True, len(valid) - 1))
        )
        self.assertFalse(any(path.name.startswith(".upload-") for path in self.mods.iterdir()))
        broken = FakeUpload("broken.jar", b"broken")
        self.assert_business_error(
            400, lambda: asyncio.run(self.service.upload(broken, True, 1024))
        )
        result = asyncio.run(self.service.upload(FakeUpload("good.jar", valid), False, len(valid)))
        self.assertEqual(result["mod"]["filename"], "good.jar.disabled")
        self.assertFalse(result["needs_restart"])
        self.assert_business_error(
            409, lambda: asyncio.run(self.service.upload(FakeUpload("good.jar", valid), True, len(valid)))
        )

    def test_trash_restore_conflict_and_purge(self):
        path = self.write_jar("trash.jar.disabled", {"fabric.mod.json": fabric_meta("trash")})
        trashed = self.service.trash(path.name)
        items = self.service.list_trash()["items"]
        self.assertEqual(items[0]["filename"], path.name)
        self.write_jar(path.name, {"fabric.mod.json": fabric_meta("replacement")})
        self.assert_business_error(409, lambda: self.service.restore(trashed["trash_id"]))
        (self.mods / path.name).unlink()
        restored = self.service.restore(trashed["trash_id"])
        self.assertEqual(restored["filename"], path.name)

        trashed_again = self.service.trash(path.name)
        purged = self.service.purge(trashed_again["trash_id"])
        self.assertEqual(purged["effective_after"], "next_start")
        self.assertEqual(self.service.list_trash()["items"], [])

    def test_config_scan_association_utf8_and_path_security(self):
        config = self.root / "config"
        config.mkdir()
        associated = config / "example.toml"
        associated.write_text('message = "你好"\n', encoding="utf-8")
        nested = config / "example"
        nested.mkdir()
        structured = nested / "settings.json"
        structured.write_text('{"enabled": true}\n', encoding="utf-8")
        all_files = self.service.list_configs("example", associated_only=False)
        associated_files = self.service.list_configs("example", associated_only=True)
        self.assertEqual(len(all_files), 2)
        self.assertEqual({item["association"] for item in associated_files}, {"exact"})
        loaded = self.service.load_config("config/example/settings.json")
        self.assertTrue(loaded["structured"])
        self.service.save_config("config/example.toml", content='message = "再见"\n', config_data=None)
        self.assertIn("再见", associated.read_text(encoding="utf-8"))
        self.assert_business_error(403, lambda: self.service.load_config("../outside.json"))

    def test_list_mods_scans_config_files_once_for_all_mods(self):
        self.write_jar("first.jar", {"fabric.mod.json": fabric_meta("first")})
        self.write_jar("second.jar", {"fabric.mod.json": fabric_meta("second")})
        config = self.root / "config"
        config.mkdir()
        (config / "first.toml").write_text("enabled = true\n", encoding="utf-8")
        (config / "second.toml").write_text("enabled = true\n", encoding="utf-8")
        with patch.object(self.service, "_iter_config_files", wraps=self.service._iter_config_files) as iterator:
            mods = {item["id"]: item for item in self.service.list_mods()["mods"]}
        self.assertEqual(iterator.call_count, 1)
        self.assertEqual(mods["first"]["config_count"], 1)
        self.assertEqual(mods["second"]["config_count"], 1)

    @unittest.skipUnless(hasattr(os, "symlink"), "当前平台不支持符号链接")
    def test_config_symlink_outside_root_is_not_listed(self):
        outside = self.root.parent / f"outside-{self.root.name}.json"
        outside.write_text("{}", encoding="utf-8")
        config = self.root / "config"
        config.mkdir()
        link = config / "outside.json"
        try:
            os.symlink(outside, link)
        except OSError:
            self.skipTest("当前环境不允许创建符号链接")
        try:
            self.assertEqual(self.service.list_configs(), [])
            self.assert_business_error(403, lambda: self.service.load_config("config/outside.json"))
        finally:
            outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
