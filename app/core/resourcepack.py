# -*- coding: utf-8 -*-
"""刷机匣 Config.xml 资源包解析。

支持 zip 资源包，读取 Brand/Series/Model，并把 DA1/DA2/Preloader
解压到本地工作目录。只读取公开的配置和固件文件。
"""
import hashlib
import os
import re
import xml.etree.ElementTree as ET
import zipfile

from . import config


class Model(object):
    def __init__(self, brand, series, attrs):
        self.brand = brand
        self.series = series
        self.name = attrs.get("Name", "")
        self.exploit = attrs.get("Exploit", "None")
        self.da1_addr = int(attrs.get("DA1Address", "0") or 0)
        self.da1 = attrs.get("DA1", "")
        self.da2_addr = int(attrs.get("DA2Address", "0") or 0)
        self.da2 = attrs.get("DA2", "")
        self.da3_addr = int(attrs.get("DA3Address", "0") or 0)
        self.da3 = attrs.get("DA3", "")
        self.payload_addr = int(attrs.get("DAPayloadAddress", "0") or 0)
        self.preloader = attrs.get("Preloader", "")
        self.description = attrs.get("Description", "")
        self.local = {}

    @property
    def label(self):
        d = self.description or self.name
        return "%s  —  %s" % (self.name, d) if d and d != self.name else self.name

    def __repr__(self):
        return "<Model %s %s>" % (self.brand, self.name)


class ResourcePack(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.info = {}
        self.brands = []          # [(brand_name, [(series_name, [Model])])]
        self.models = []
        self._zip = zipfile.ZipFile(self.path)
        self._entries = self._zip.namelist()
        cfg = None
        for n in self._entries:
            if n.lower().endswith("config.xml"):
                cfg = n
                break
        if not cfg:
            raise ValueError("资源包缺少 Config.xml")
        self._cfg = cfg
        root = ET.fromstring(self._zip.read(cfg))
        info = root.find("PacketInfo")
        if info is not None:
            self.info = dict(info.attrib)
        for b in root.findall("Brand"):
            bname = b.get("Name", "")
            series_list = []
            for s in b.findall("Series"):
                sname = s.get("Name", "")
                models = [Model(bname, sname, m.attrib) for m in s.findall("Model")]
                models = [m for m in models if m.name]
                if models:
                    series_list.append((sname, models))
                    self.models.extend(models)
            if series_list:
                self.brands.append((bname, series_list))

    @property
    def publisher(self):
        return self.info.get("Publisher", "")

    @property
    def version(self):
        return self.info.get("PublishVersion", "")

    @property
    def publish_date(self):
        return self.info.get("PublishDate", "")

    @property
    def tip(self):
        return self.info.get("Tip", "")

    def _find(self, remote):
        if not remote:
            return None
        want = remote.replace("\\", "/").lstrip("/").lower()
        for n in self._entries:
            nn = n.replace("\\", "/").lower()
            if nn == want or nn.endswith("/" + want):
                return n
        return None

    def extract(self, model, dest=None):
        """解压一个机型的 DA/Preloader，返回本地路径字典。"""
        dest = dest or os.path.join(config.WORK, "resource_packs",
                                    re.sub(r"[^A-Za-z0-9_.-]+", "_", model.name))
        os.makedirs(dest, exist_ok=True)
        out = {}
        for key, remote in (("da1", model.da1), ("da2", model.da2),
                            ("da3", model.da3), ("preloader", model.preloader)):
            if not remote:
                continue
            n = self._find(remote)
            if not n:
                raise ValueError("资源包缺少 %s：%s" % (key, remote))
            base = os.path.basename(n)
            target = os.path.join(dest, base)
            with self._zip.open(n) as src, open(target + ".tmp", "wb") as dst:
                while True:
                    buf = src.read(1024 * 1024)
                    if not buf:
                        break
                    dst.write(buf)
            os.replace(target + ".tmp", target)
            out[key] = target
        model.local = out
        return out

    def close(self):
        try:
            self._zip.close()
        except Exception:
            pass


def load(path):
    return ResourcePack(path)


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
