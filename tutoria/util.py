from contextlib import contextmanager
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import json
import os
import re
import tempfile

from .types import TutorError


def digest(value: bytes | dict | list | str) -> str:
    if not isinstance(value, bytes):
        value = (value if isinstance(value, str) else json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )).encode("utf-8")
    return sha256(value).hexdigest()


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        raise TutorError(f"Dependência ausente: {name}. Execute pip install -r requirements.txt.") from None


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise TutorError(f"Não foi possível ler {path.name}. Restaure o arquivo ou use outra pasta de dados.") from None


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".writing-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def safe_name(name: str) -> str:
    basename = name.replace("\\", "/").rsplit("/", 1)[-1]
    basename = re.sub(r"[^\w.\- ]", "_", basename, flags=re.UNICODE).strip(" .")
    if not basename or len(basename) > 180:
        raise TutorError("Use um nome de arquivo de até 180 caracteres.")
    return basename


def artifact_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise TutorError("Caminho de material inválido.")
    return path


@contextmanager
def data_lock(root: Path):
    from filelock import FileLock, Timeout

    root.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(root / ".data.lock"), timeout=2):
            yield
    except Timeout:
        raise TutorError("Há outra operação na base. Aguarde a indexação terminar e tente novamente.") from None
