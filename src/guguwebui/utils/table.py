# -*- coding: utf-8 -*-
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import anyio
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True


class Table:
    """A json/yml file reader with save function.
    It also can auto-save when first level for dict changes.

    Args:
        path (str, Path): path for the config, will generate one if not exist
        default_content (Optional[dict]): default value when generating
        use_yaml (Optional[bool]): store it as yaml file
    """

    def __init__(
            self,
            path: str = "./default.json",
            default_content: dict = None,
            use_yaml: bool = False
    ) -> None:
        self.data: Any = None
        self.use_yaml = use_yaml
        self.path = path if not self.use_yaml else path.replace(".json", ".yml")
        self.path = Path(self.path)
        self.default_content = default_content
        self._lock = asyncio.Lock()
        self.load()

    def load(self) -> None:  # loading
        if os.path.isfile(self.path) and os.path.getsize(self.path) != 0:
            with open(self.path, 'r', encoding='UTF-8') as f:
                if self.use_yaml:
                    self.data = yaml.load(f)
                else:
                    self.data = json.load(f)
        else:  # file not exists -> create new one
            self.data = self.default_content if self.default_content else {}
            self.save()

    def save(self) -> None:  # synchronous saving for compatibility
        self.path.parents[0].mkdir(parents=True, exist_ok=True)
        if self.use_yaml:
            with open(self.path, 'w', encoding='UTF-8') as f:
                yaml.dump(self.data, f)
        else:
            with open(self.path, 'w', encoding='UTF-8') as f:
                json.dump(self.data, f, ensure_ascii=False)

    async def save_async(self) -> None:  # asynchronous saving
        async with self._lock:
            await anyio.Path(self.path.parent).mkdir(parents=True, exist_ok=True)
            if self.use_yaml:
                # ruamel.yaml doesn't support async dump directly, use run_in_executor
                def dump_yaml():
                    with open(self.path, 'w', encoding='UTF-8') as file:
                        yaml.dump(self.data, file)

                await asyncio.get_event_loop().run_in_executor(None, dump_yaml)
            else:
                content = json.dumps(self.data, ensure_ascii=False)
                async with await anyio.open_file(self.path, mode='w', encoding='UTF-8') as f:
                    await f.write(content)

    def __getitem__(self, key: str):  # get item like dict[key]
        return self.data[key]

    def __setitem__(self, key: str, value):  # auto-save (still sync for now to avoid breaking existing code)
        self.data[key] = value
        self.save()

    def __contains__(self, key: str):  # in
        return key in self.data

    def __delitem__(self, key: str):  # del like del dict[key]
        if key in self.data:
            del self.data[key]
            self.save()

    def __iter__(self):
        return iter(self.data.keys())

    def __repr__(self) -> str:  # print the dict
        if self.data is None:
            return ""
        return str(self.data)

    def __len__(self):
        return len(self.data)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def keys(self):
        return self.data.keys()

    def values(self):
        return self.data.values()

    def items(self):
        return self.data.items()
