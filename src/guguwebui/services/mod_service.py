from __future__ import annotations

import datetime
import io
import json
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import javaproperties

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from guguwebui.structures import BusinessException
from guguwebui.utils.mc_util import get_minecraft_path


_METADATA_LIMIT = 2 * 1024 * 1024
_ICON_LIMIT = 2 * 1024 * 1024
_CONFIG_SUFFIXES = {".json", ".json5", ".yml", ".yaml", ".properties", ".toml", ".cfg", ".conf"}
_BUILTIN_DEPENDENCIES = {
    "minecraft", "java", "fabricloader", "fabric-loader", "quilt_loader",
    "forge", "neoforge", "neoforge_loader", "mcp",
}
_SAFE_ID_RE = re.compile(r"[^a-z0-9]+")


class ModService:
    def __init__(self, server, config_service=None):
        self.server = server
        self.config_service = config_service
        self._lock = threading.RLock()
        self._metadata_cache: dict[tuple[str, int, int], dict] = {}

    def working_dir(self) -> Path:
        return Path(get_minecraft_path(self.server, "working_directory")).resolve()

    def mods_dir(self) -> Path:
        path = self.working_dir() / "mods"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def trash_dir(self) -> Path:
        path = self.working_dir() / ".guguwebui" / "mod-trash"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _server_running(self) -> bool:
        try:
            return bool(self.server.is_server_running() or self.server.is_server_startup())
        except Exception:
            return False

    def _operation_state(self, warnings: Optional[list] = None, *, affects_loaded_state: bool = True) -> dict:
        running = self._server_running()
        needs_restart = running and affects_loaded_state
        return {
            "server_running": running,
            "needs_restart": needs_restart,
            "effective_after": "restart" if needs_restart else "next_start",
            "warnings": warnings or [],
        }

    def _server_loader(self) -> Optional[str]:
        """从明确的启动命令标记中尽力识别服务端 Loader。"""
        try:
            config = self.server.get_mcdr_config()
            command = getattr(config, "start_command", None)
            if command is None and isinstance(config, dict):
                command = config.get("start_command")
        except Exception:
            command = None
        if isinstance(command, (list, tuple)):
            command = " ".join(str(part) for part in command)
        normalized = str(command or "").lower().replace("\\", "/")
        if not normalized:
            return None
        if "neoforge" in normalized:
            return "neoforge"
        if "quilt" in normalized:
            return "quilt"
        if "fabric" in normalized:
            return "fabric"
        if re.search(r"(?:^|[/_.-])forge(?:[/_.-]|$)", normalized):
            return "forge"
        return None

    @staticmethod
    def _rename_no_replace(source: Path, target: Path) -> None:
        """在同一文件系统中移动文件，目标存在时绝不覆盖。"""
        if target.exists():
            raise FileExistsError(str(target))
        if os.name == "nt":
            # Windows 的 MoveFile 语义在目标存在时会失败。
            os.rename(source, target)
            return
        # POSIX rename() 会覆盖目标。硬链接创建具有原子的 O_EXCL 语义，随后
        # 删除旧目录项即可完成同文件系统内的无覆盖移动。
        os.link(source, target, follow_symlinks=False)
        try:
            source.unlink()
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @staticmethod
    def _raise_file_operation_error(exc: OSError, action: str) -> None:
        """把 Windows 文件占用等底层错误转换为面板可理解的响应。"""
        if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32, 33}:
            raise BusinessException(
                f"模组文件正被 Minecraft 服务器或其他进程占用，无法{action}。请先停止服务器并关闭占用该文件的程序后重试。",
                status_code=423,
            ) from exc
        raise BusinessException(f"无法{action}模组文件: {exc}", status_code=500) from exc

    @staticmethod
    def _validate_filename(filename: str) -> str:
        filename = str(filename or "").strip()
        if not filename or Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise BusinessException("无效的模组文件名")
        if not (filename.lower().endswith(".jar") or filename.lower().endswith(".jar.disabled")):
            raise BusinessException("仅支持 .jar 或 .jar.disabled 模组文件")
        return filename

    def _mod_path(self, filename: str, *, must_exist: bool = True) -> Path:
        filename = self._validate_filename(filename)
        base = self.mods_dir().resolve()
        candidate = base / filename
        if candidate.is_symlink():
            raise BusinessException("模组文件不能是符号链接", status_code=403)
        path = candidate.resolve()
        if path.parent != base:
            raise BusinessException("模组路径越界", status_code=403)
        if must_exist and not path.is_file():
            raise BusinessException("模组文件不存在", status_code=404)
        return path

    @staticmethod
    def _read_zip_entry(zf: zipfile.ZipFile, name: str, limit: int) -> Optional[bytes]:
        try:
            info = zf.getinfo(name)
        except KeyError:
            return None
        if info.is_dir() or info.file_size < 0 or info.file_size > limit:
            return None
        if info.compress_size > 0 and info.file_size / info.compress_size > 200:
            return None
        with zf.open(info, "r") as fp:
            data = fp.read(limit + 1)
        return data if len(data) <= limit else None

    @staticmethod
    def _authors(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [str(k) for k in value.keys()]
        result = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("id")
                    if name:
                        result.append(str(name))
        return result

    @staticmethod
    def _dependency_list(value: Any, *, forge: bool = False) -> list[dict]:
        result: list[dict] = []
        if isinstance(value, dict):
            for dep_id, constraint in value.items():
                result.append({"id": str(dep_id), "version": str(constraint), "mandatory": True})
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    result.append({"id": item, "version": "*", "mandatory": True})
                elif isinstance(item, dict):
                    dep_id = item.get("modId" if forge else "id") or item.get("id")
                    if not dep_id:
                        continue
                    result.append({
                        "id": str(dep_id),
                        "version": str(item.get("versionRange") or item.get("versions") or item.get("version") or "*"),
                        "mandatory": bool(item.get("mandatory", True)),
                    })
        return result

    @classmethod
    def _forge_dependency_lists(cls, value: Any) -> tuple[list[dict], list[dict]]:
        dependencies: list[dict] = []
        conflicts: list[dict] = []
        for item in value if isinstance(value, list) else []:
            if not isinstance(item, dict):
                continue
            dep_id = item.get("modId") or item.get("id")
            if not dep_id:
                continue
            dep_type = str(item.get("type") or "").lower()
            parsed = cls._dependency_list([item], forge=True)
            if not parsed:
                continue
            if dep_type in {"incompatible", "discouraged"}:
                conflicts.extend(parsed)
            else:
                if dep_type == "optional":
                    parsed[0]["mandatory"] = False
                dependencies.extend(parsed)
        return dependencies, conflicts

    def _parse_metadata(self, path: Path) -> dict:
        stat = path.stat()
        cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        cached = self._metadata_cache.get(cache_key)
        if cached is not None:
            return cached
        fallback = {
            "id": path.name.removesuffix(".disabled").removesuffix(".jar"),
            "name": path.name.removesuffix(".disabled").removesuffix(".jar"),
            "version": "",
            "authors": [],
            "description": "",
            "loader": "unknown",
            "environment": "*",
            "dependencies": [],
            "conflicts": [],
            "icon_entry": None,
            "recognized": False,
            "parse_error": None,
        }
        try:
            with zipfile.ZipFile(path, "r") as zf:
                raw = self._read_zip_entry(zf, "fabric.mod.json", _METADATA_LIMIT)
                if raw is not None:
                    data = json.loads(raw.decode("utf-8-sig"))
                    icon = data.get("icon")
                    if isinstance(icon, dict):
                        icon = next(
                            (value for _size, value in sorted(icon.items(), key=lambda item: str(item[0]), reverse=True) if isinstance(value, str)),
                            None,
                        )
                    metadata = {
                        **fallback,
                        "id": str(data.get("id") or fallback["id"]),
                        "name": str(data.get("name") or data.get("id") or fallback["name"]),
                        "version": str(data.get("version") or ""),
                        "authors": self._authors(data.get("authors")),
                        "description": str(data.get("description") or ""),
                        "loader": "fabric",
                        "environment": str(data.get("environment") or "*"),
                        "dependencies": self._dependency_list(data.get("depends")),
                        "conflicts": self._dependency_list(data.get("breaks")) + self._dependency_list(data.get("conflicts")),
                        "icon_entry": icon if isinstance(icon, str) else None,
                        "recognized": True,
                    }
                    self._metadata_cache[cache_key] = metadata
                    return metadata

                raw = self._read_zip_entry(zf, "quilt.mod.json", _METADATA_LIMIT)
                if raw is not None:
                    data = json.loads(raw.decode("utf-8-sig"))
                    ql = data.get("quilt_loader") or {}
                    meta = ql.get("metadata") or {}
                    metadata = {
                        **fallback,
                        "id": str(ql.get("id") or fallback["id"]),
                        "name": str(meta.get("name") or ql.get("id") or fallback["name"]),
                        "version": str(ql.get("version") or ""),
                        "authors": self._authors(meta.get("contributors")),
                        "description": str(meta.get("description") or ""),
                        "loader": "quilt",
                        "dependencies": self._dependency_list(ql.get("depends")),
                        "conflicts": self._dependency_list(ql.get("breaks")),
                        "icon_entry": meta.get("icon") if isinstance(meta.get("icon"), str) else None,
                        "recognized": True,
                    }
                    self._metadata_cache[cache_key] = metadata
                    return metadata

                for entry, loader in (("META-INF/neoforge.mods.toml", "neoforge"), ("META-INF/mods.toml", "forge")):
                    raw = self._read_zip_entry(zf, entry, _METADATA_LIMIT)
                    if raw is None:
                        continue
                    data = tomllib.loads(raw.decode("utf-8-sig"))
                    mods = data.get("mods") or []
                    mod = mods[0] if isinstance(mods, list) and mods else {}
                    mod_id = str(mod.get("modId") or fallback["id"])
                    dep_map = data.get("dependencies") or {}
                    dep_value = dep_map.get(mod_id, []) if isinstance(dep_map, dict) else []
                    dependencies, conflicts = self._forge_dependency_lists(dep_value)
                    metadata = {
                        **fallback,
                        "id": mod_id,
                        "name": str(mod.get("displayName") or mod_id),
                        "version": str(mod.get("version") or ""),
                        "authors": self._authors(mod.get("authors")),
                        "description": str(mod.get("description") or ""),
                        "loader": loader,
                        "dependencies": dependencies,
                        "conflicts": conflicts,
                        "icon_entry": mod.get("logoFile") if isinstance(mod.get("logoFile"), str) else None,
                        "recognized": True,
                    }
                    self._metadata_cache[cache_key] = metadata
                    return metadata

                manifest = self._read_zip_entry(zf, "META-INF/MANIFEST.MF", _METADATA_LIMIT)
                if manifest:
                    attrs: dict[str, str] = {}
                    for line in manifest.decode("utf-8", errors="replace").splitlines():
                        if ":" in line:
                            key, value = line.split(":", 1)
                            attrs[key.strip()] = value.strip()
                    fallback["name"] = attrs.get("Implementation-Title", fallback["name"])
                    fallback["version"] = attrs.get("Implementation-Version", "")
                self._metadata_cache[cache_key] = fallback
                return fallback
        except (zipfile.BadZipFile, OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            fallback["parse_error"] = str(exc)
            self._metadata_cache[cache_key] = fallback
            return fallback

    @staticmethod
    def _normalized_id(value: str) -> str:
        return _SAFE_ID_RE.sub("", str(value or "").lower())

    def _config_roots(self) -> list[Path]:
        working = self.working_dir()
        roots = [working / "config", working / "defaultconfigs"]
        level_name = "world"
        props = working / "server.properties"
        try:
            if props.is_file():
                with open(props, "r", encoding="utf-8") as fp:
                    level_name = str(javaproperties.load(fp).get("level-name") or "world")
        except Exception:
            pass
        roots.append(working / level_name / "serverconfig")
        try:
            for child in working.iterdir():
                candidate = child / "serverconfig"
                if child.is_dir() and candidate.is_dir():
                    roots.append(candidate)
        except OSError:
            pass
        unique: list[Path] = []
        seen = set()
        for root in roots:
            resolved = root.resolve()
            try:
                resolved.relative_to(working.resolve())
            except ValueError:
                continue
            if resolved not in seen:
                seen.add(resolved)
                unique.append(resolved)
        return unique

    @staticmethod
    def _config_association(path: Path, root: Path, normalized_mod_id: str) -> Optional[str]:
        if not normalized_mod_id:
            return None
        component_ids = [_SAFE_ID_RE.sub("", part.lower()) for part in path.relative_to(root).parts[:-1]]
        stem = _SAFE_ID_RE.sub("", path.stem.lower())
        if normalized_mod_id in component_ids or stem == normalized_mod_id:
            return "exact"
        if stem.startswith(normalized_mod_id) or normalized_mod_id.startswith(stem):
            return "prefix"
        return None

    def _config_counts(self, mod_ids: Iterable[str]) -> dict[str, int]:
        """只遍历配置目录一次，批量计算模组关联配置数量。"""
        normalized_ids = {self._normalized_id(mod_id) for mod_id in mod_ids}
        normalized_ids.discard("")
        counts = {mod_id: 0 for mod_id in normalized_ids}
        if not counts:
            return counts
        for path, root in self._iter_config_files():
            for mod_id in counts:
                if self._config_association(path, root, mod_id):
                    counts[mod_id] += 1
        return counts

    def _scan_entries(self, *, include_config_count: bool = True) -> list[dict]:
        result = []
        try:
            files = sorted(self.mods_dir().iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            raise BusinessException(f"无法读取模组目录: {exc}", status_code=500)
        names = {p.name.lower() for p in files if p.is_file()}
        scanned: list[tuple[Path, bool, dict, os.stat_result]] = []
        for path in files:
            lower = path.name.lower()
            if not path.is_file() or not (lower.endswith(".jar") or lower.endswith(".jar.disabled")):
                continue
            enabled = lower.endswith(".jar")
            metadata = self._parse_metadata(path)
            stat = path.stat()
            scanned.append((path, enabled, metadata, stat))
        config_counts = self._config_counts(metadata["id"] for _path, _enabled, metadata, _stat in scanned) if include_config_count else {}
        for path, enabled, metadata, stat in scanned:
            counterpart = (path.name + ".disabled") if enabled else path.name[:-9]
            entry = {
                "filename": path.name,
                "enabled": enabled,
                "size": stat.st_size,
                "modified_at": datetime.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                "file_conflict": counterpart.lower() in names,
                "config_count": config_counts.get(self._normalized_id(metadata["id"]), 0),
                **{k: v for k, v in metadata.items() if k != "icon_entry"},
                "has_icon": bool(metadata.get("icon_entry")),
                "warnings": [],
            }
            result.append(entry)
        self._apply_warnings(result)
        return result

    def _apply_warnings(self, entries: list[dict]) -> None:
        enabled = [entry for entry in entries if entry["enabled"]]
        server_loader = self._server_loader()
        id_map: dict[str, list[dict]] = {}
        for entry in enabled:
            id_map.setdefault(str(entry["id"]).lower(), []).append(entry)
        enabled_ids = set(id_map)
        for mod_id, duplicates in id_map.items():
            if mod_id and len(duplicates) > 1:
                for entry in duplicates:
                    entry["warnings"].append({"code": "duplicate_id", "message": f"存在重复模组 ID: {entry['id']}"})
        for entry in entries:
            if entry.get("file_conflict"):
                entry["warnings"].append({"code": "file_conflict", "message": "同时存在启用和禁用状态的同名文件"})
            if entry.get("parse_error"):
                entry["warnings"].append({"code": "invalid_jar", "message": "JAR 无法解析或已损坏"})
            elif not entry.get("recognized"):
                entry["warnings"].append({"code": "unknown_metadata", "message": "未识别到标准模组元数据"})
            if not entry["enabled"]:
                continue
            mod_loader = str(entry.get("loader") or "unknown").lower()
            compatible = (
                mod_loader in {"unknown", server_loader}
                or (server_loader == "quilt" and mod_loader == "fabric")
            )
            if server_loader and not compatible:
                entry["warnings"].append({
                    "code": "loader_mismatch",
                    "message": f"模组 Loader 为 {mod_loader}，当前服务端启动命令识别为 {server_loader}",
                })
            for dep in entry.get("dependencies") or []:
                dep_id = str(dep.get("id") or "").lower()
                if dep.get("mandatory", True) and dep_id and dep_id not in _BUILTIN_DEPENDENCIES and dep_id not in enabled_ids:
                    entry["warnings"].append({"code": "missing_dependency", "message": f"缺少必需依赖: {dep.get('id')} {dep.get('version', '')}".strip()})
            for conflict in entry.get("conflicts") or []:
                conflict_id = str(conflict.get("id") or "").lower()
                if conflict_id in enabled_ids:
                    entry["warnings"].append({"code": "declared_conflict", "message": f"与已启用模组冲突: {conflict.get('id')}"})

    def list_mods(self) -> dict:
        entries = self._scan_entries()
        return {
            "status": "success",
            "mods": entries,
            "server_running": self._server_running(),
            "mods_path": str(self.mods_dir()),
        }

    def get_icon(self, filename: str) -> tuple[bytes, str]:
        path = self._mod_path(filename)
        metadata = self._parse_metadata(path)
        entry = metadata.get("icon_entry")
        if not isinstance(entry, str) or entry.startswith(("/", "\\")) or ".." in Path(entry).parts:
            raise BusinessException("该模组没有可用图标", status_code=404)
        try:
            with zipfile.ZipFile(path, "r") as zf:
                data = self._read_zip_entry(zf, entry.replace("\\", "/"), _ICON_LIMIT)
        except zipfile.BadZipFile:
            data = None
        if not data:
            raise BusinessException("该模组没有可用图标", status_code=404)
        media_type = mimetypes.guess_type(entry)[0] or "application/octet-stream"
        if not media_type.startswith("image/"):
            raise BusinessException("模组图标格式不受支持", status_code=415)
        return data, media_type

    def toggle(self, filename: str, enabled: bool, acknowledge_warnings: bool = False) -> dict:
        with self._lock:
            source = self._mod_path(filename)
            currently_enabled = source.name.lower().endswith(".jar")
            if currently_enabled == enabled:
                return {
                    "status": "success",
                    "message": "模组状态未变化",
                    **self._operation_state(affects_loaded_state=False),
                }
            target_name = source.name[:-9] if enabled else source.name + ".disabled"
            target = self._mod_path(target_name, must_exist=False)
            if target.exists():
                raise BusinessException("目标文件已存在，无法切换状态", status_code=409)

            entries = self._scan_entries(include_config_count=False)
            for entry in entries:
                if entry["filename"] == source.name:
                    entry["enabled"] = enabled
                    entry["filename"] = target_name
                    entry["warnings"] = []
            for entry in entries:
                entry["warnings"] = []
            self._apply_warnings(entries)
            affected = next((item for item in entries if item["filename"] == target_name), None)
            warnings = list((affected or {}).get("warnings") or [])
            if not enabled:
                disabled_id = str((affected or {}).get("id") or "").lower()
                for item in entries:
                    if not item["enabled"]:
                        continue
                    for dep in item.get("dependencies") or []:
                        if str(dep.get("id") or "").lower() == disabled_id and dep.get("mandatory", True):
                            warnings.append({"code": "reverse_dependency", "message": f"{item['name']} 依赖此模组"})
            actionable = [w for w in warnings if w.get("code") not in {"unknown_metadata"}]
            if actionable and not acknowledge_warnings:
                raise BusinessException("操作存在兼容性警告，请确认后重试", status_code=409, data={"warnings": warnings})
            try:
                self._rename_no_replace(source, target)
            except FileExistsError:
                raise BusinessException("目标文件已存在，无法切换状态", status_code=409)
            except OSError as exc:
                self._raise_file_operation_error(exc, "切换")
            return {"status": "success", "message": "模组状态已更新", "filename": target_name, **self._operation_state(warnings)}

    async def upload(self, upload_file, enabled: bool, max_bytes: int, acknowledge_warnings: bool = False) -> dict:
        raw_name = Path(str(upload_file.filename or "")).name
        if Path(raw_name).name != str(upload_file.filename or "") or not raw_name.lower().endswith(".jar"):
            raise BusinessException("请选择有效的 .jar 文件")
        target_name = raw_name if enabled else raw_name + ".disabled"
        target = self._mod_path(target_name, must_exist=False)
        counterpart = self._mod_path(raw_name + ".disabled" if enabled else raw_name, must_exist=False)
        if target.exists() or counterpart.exists():
            raise BusinessException("同名模组文件已存在", status_code=409)
        fd, temp_name = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=str(self.mods_dir()))
        size = 0
        try:
            with os.fdopen(fd, "wb") as fp:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise BusinessException("模组文件超过上传大小限制", status_code=413)
                    fp.write(chunk)
                fp.flush()
                os.fsync(fp.fileno())
            try:
                # ZipFile 会校验中央目录；元数据读取时再校验受限条目，避免上传阶段
                # 为了 testzip() 解压整份可能很大的 JAR。
                with zipfile.ZipFile(temp_name, "r") as zf:
                    if not zf.namelist():
                        raise BusinessException("上传文件不是有效的 JAR/ZIP")
            except zipfile.BadZipFile:
                raise BusinessException("上传文件不是有效的 JAR/ZIP")
            metadata = self._parse_metadata(Path(temp_name))
            if metadata.get("parse_error"):
                raise BusinessException("上传的 JAR 文件无法解析")
            with self._lock:
                if target.exists() or counterpart.exists():
                    raise BusinessException("同名模组文件已存在", status_code=409)
                entries = self._scan_entries(include_config_count=False)
                candidate_stat = os.stat(temp_name)
                candidate = {
                    "filename": target_name,
                    "enabled": enabled,
                    "size": candidate_stat.st_size,
                    "modified_at": datetime.datetime.now().astimezone().isoformat(),
                    "file_conflict": False,
                    "config_count": 0,
                    **{k: v for k, v in metadata.items() if k != "icon_entry"},
                    "has_icon": bool(metadata.get("icon_entry")),
                    "warnings": [],
                }
                entries.append(candidate)
                self._apply_warnings(entries)
                warnings = list(candidate.get("warnings") or [])
                actionable = [w for w in warnings if w.get("code") not in {"unknown_metadata"}]
                if actionable and not acknowledge_warnings:
                    raise BusinessException(
                        "上传存在兼容性警告，请确认后重试",
                        status_code=409,
                        data={"warnings": warnings},
                    )
                try:
                    self._rename_no_replace(Path(temp_name), target)
                except FileExistsError:
                    raise BusinessException("同名模组文件已存在", status_code=409)
                except OSError as exc:
                    self._raise_file_operation_error(exc, "保存")
            item = next((m for m in self._scan_entries() if m["filename"] == target_name), None)
            return {
                "status": "success",
                "message": "模组上传成功",
                "mod": item,
                **self._operation_state((item or {}).get("warnings"), affects_loaded_state=enabled),
            }
        finally:
            try:
                await upload_file.close()
            except Exception:
                pass
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def trash(self, filename: str) -> dict:
        with self._lock:
            source = self._mod_path(filename)
            trash_id = str(uuid.uuid4())
            destination_dir = self.trash_dir() / trash_id
            destination_dir.mkdir(parents=True, exist_ok=False)
            metadata = self._parse_metadata(source)
            manifest = {
                "id": trash_id,
                "filename": source.name,
                "enabled": source.name.lower().endswith(".jar"),
                "deleted_at": datetime.datetime.now().astimezone().isoformat(),
                "metadata": {k: v for k, v in metadata.items() if k != "icon_entry"},
            }
            was_enabled = manifest["enabled"]
            try:
                os.replace(source, destination_dir / source.name)
                self._write_json_atomic(destination_dir / "manifest.json", manifest)
            except Exception as exc:
                if (destination_dir / source.name).exists() and not source.exists():
                    os.replace(destination_dir / source.name, source)
                shutil.rmtree(destination_dir, ignore_errors=True)
                if isinstance(exc, OSError):
                    self._raise_file_operation_error(exc, "删除")
                raise
            return {
                "status": "success",
                "message": "模组已移入回收站",
                "trash_id": trash_id,
                **self._operation_state(affects_loaded_state=was_enabled),
            }

    @staticmethod
    def _write_json_atomic(path: Path, data: Any) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        with open(temp, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp, path)

    def list_trash(self) -> dict:
        items = []
        for directory in sorted(self.trash_dir().iterdir(), reverse=True):
            manifest_path = directory / "manifest.json"
            if not directory.is_dir() or not manifest_path.is_file():
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as fp:
                    manifest = json.load(fp)
                filename = self._validate_filename(manifest.get("filename", ""))
                if (directory / filename).is_file():
                    items.append(manifest)
            except Exception:
                continue
        return {"status": "success", "items": items}

    def _trash_item(self, trash_id: str) -> tuple[Path, dict, Path]:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", trash_id or ""):
            raise BusinessException("无效的回收站 ID")
        directory = (self.trash_dir() / trash_id).resolve()
        if directory.parent != self.trash_dir().resolve():
            raise BusinessException("回收站路径越界", status_code=403)
        try:
            with open(directory / "manifest.json", "r", encoding="utf-8") as fp:
                manifest = json.load(fp)
            filename = self._validate_filename(manifest.get("filename", ""))
        except FileNotFoundError:
            raise BusinessException("回收站项目不存在", status_code=404)
        source = directory / filename
        if source.is_symlink() or not source.is_file():
            raise BusinessException("回收站文件不存在", status_code=404)
        return directory, manifest, source

    def restore(self, trash_id: str) -> dict:
        with self._lock:
            directory, manifest, source = self._trash_item(trash_id)
            target = self._mod_path(manifest["filename"], must_exist=False)
            if target.exists():
                raise BusinessException("mods 目录中已存在同名文件", status_code=409)
            try:
                self._rename_no_replace(source, target)
            except FileExistsError:
                raise BusinessException("mods 目录中已存在同名文件", status_code=409)
            except OSError as exc:
                self._raise_file_operation_error(exc, "恢复")
            shutil.rmtree(directory, ignore_errors=True)
            return {
                "status": "success",
                "message": "模组已恢复",
                "filename": target.name,
                **self._operation_state(affects_loaded_state=bool(manifest.get("enabled"))),
            }

    def purge(self, trash_id: str) -> dict:
        with self._lock:
            directory, manifest, _source = self._trash_item(trash_id)
            shutil.rmtree(directory)
            return {
                "status": "success",
                "message": "回收站项目已永久删除",
                "filename": manifest["filename"],
                **self._operation_state(affects_loaded_state=False),
            }

    def _iter_config_files(self) -> Iterable[tuple[Path, Path]]:
        for root in self._config_roots():
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in _CONFIG_SUFFIXES:
                    continue
                try:
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(root)
                    resolved.relative_to(self.working_dir())
                except (OSError, ValueError):
                    continue
                yield resolved, root

    def list_configs(self, mod_id: Optional[str] = None, associated_only: bool = False) -> list[dict]:
        normalized = self._normalized_id(mod_id or "")
        result = []
        for path, root in self._iter_config_files():
            relative = path.relative_to(self.working_dir()).as_posix()
            association = self._config_association(path, root, normalized)
            if associated_only and not association:
                continue
            result.append({
                "path": relative,
                "name": path.name,
                "root": root.relative_to(self.working_dir()).as_posix(),
                "association": association,
                "structured": path.suffix.lower() in {".json", ".yml", ".yaml", ".properties"},
                "size": path.stat().st_size,
            })
        result.sort(key=lambda item: item["path"].lower())
        return result

    def configs_response(self, mod_id: Optional[str], associated_only: bool) -> dict:
        return {"status": "success", "files": self.list_configs(mod_id, associated_only)}

    def _resolve_config_path(self, relative_path: str) -> Path:
        if not relative_path or Path(relative_path).is_absolute():
            raise BusinessException("配置路径必须是相对路径")
        unchecked = self.working_dir() / relative_path
        candidate = unchecked.resolve(strict=False)
        try:
            candidate.relative_to(self.working_dir())
        except ValueError:
            raise BusinessException("配置路径不在工作目录中", status_code=403)
        if not candidate.exists():
            raise BusinessException("配置文件不存在或格式不受支持", status_code=404)
        candidate = unchecked.resolve(strict=True)
        if candidate.suffix.lower() not in _CONFIG_SUFFIXES or not candidate.is_file():
            raise BusinessException("配置文件不存在或格式不受支持", status_code=404)
        for root in self._config_roots():
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
        raise BusinessException("配置路径不在允许的目录中", status_code=403)

    def load_config(self, relative_path: str) -> dict:
        path = self._resolve_config_path(relative_path)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise BusinessException("配置文件不是 UTF-8 文本")
        data = None
        try:
            if path.suffix.lower() == ".json":
                data = json.loads(content)
            elif path.suffix.lower() in {".yml", ".yaml"}:
                from guguwebui.utils.table import yaml
                data = yaml.load(io.StringIO(content))
            elif path.suffix.lower() == ".properties":
                data = dict(javaproperties.loads(content))
        except Exception:
            data = None
        return {
            "status": "success",
            "path": relative_path,
            "content": content,
            "config_data": data,
            "structured": path.suffix.lower() in {".json", ".yml", ".yaml", ".properties"} and data is not None,
        }

    def save_config(self, relative_path: str, *, content: Optional[str], config_data: Any) -> dict:
        path = self._resolve_config_path(relative_path)
        if content is None and config_data is None:
            raise BusinessException("缺少配置内容")
        if content is None:
            suffix = path.suffix.lower()
            if suffix == ".json":
                content = json.dumps(config_data, ensure_ascii=False, indent=2) + "\n"
            elif suffix in {".yml", ".yaml"}:
                from io import StringIO
                from guguwebui.utils.table import yaml
                stream = StringIO()
                yaml.dump(config_data, stream)
                content = stream.getvalue()
            elif suffix == ".properties":
                content = javaproperties.dumps({str(k): str(v) for k, v in dict(config_data).items()})
            else:
                raise BusinessException("该格式仅支持文本编辑")
        encoded = content.encode("utf-8")
        temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        try:
            with open(temp, "wb") as fp:
                fp.write(encoded)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return {"status": "success", "message": "模组配置已保存", "path": relative_path, **self._operation_state()}
