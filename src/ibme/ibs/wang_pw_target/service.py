"""Bounded, fixed issuance around the unchanged raw target Wang--PW IBS.

Snapshots are private plaintext.  Cooperating writers share the permanent local
OS lock from ``cli_state``.  An uncertain operation leaves a pending marker and,
when writable, a failed ledger.  There is no automatic retry, rollback recovery,
distributed lock or power-loss theorem.  This layer adds issuance policy, not a
new paper algorithm or security claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile

from ibme.cli_state import LOCK_FILE
from ibme.core.types import validate_identity
from ibme.ibs import wang_pw_service as _legacy

from .objects import MasterSecret, PublicKey, SigningKey
from .params import Params


STATE_FILE = "master.bin"
PENDING_FILE = "master.bin.pending"
MAGIC = b"WPTISS01"
MAX_STATE_BYTES = (1 << 32) - 1
MAX_USERS = 64
MAX_PARAMS_BYTES = 32768
_ENTRY_STATUS = {"pending": 0, "failed": 1, "issued": 2, "imported": 3}
_STATE_STATUS = {"ready": 0, "failed": 1}
_COMPLETE_ENTRIES = frozenset(("issued", "imported"))
_COMPLETE_ENTRY_CODES = frozenset(_ENTRY_STATUS[name] for name in _COMPLETE_ENTRIES)
_ENTRY_NAMES = {value: name for name, value in _ENTRY_STATUS.items()}

# Share error contracts and audited filesystem/lock mechanics, but neither the
# old JSON snapshot codec, its secret object classes nor its 1 MiB capacity.
IssuerStateError = _legacy.IssuerStateError
IssuerPendingError = _legacy.IssuerPendingError
IssuerCapacityError = _legacy.IssuerCapacityError


def state_size_bounds(params: Params, max_users: int) -> dict[str, int]:
    """Wire bounds only; never allocate a hypothetical matrix or consume RNG."""
    if type(params) is not Params:
        raise TypeError("exact Wang-PW target parameters required")
    if type(max_users) is not int or not 1 <= max_users <= MAX_USERS:
        raise ValueError("max_users must be an integer in 1..64")
    parameter_bytes = len(params.context())
    if parameter_bytes > MAX_PARAMS_BYTES:
        raise IssuerCapacityError("target parameter snapshot exceeds its byte budget")
    # WPTPK001 + LP32(params) + uint32 A; WPTMS001 + LP32(PK) + int16 R;
    # WPTSK001 + LP32(PK) + LP32(identity) + salt + int32 X.
    public = 8 + 4 + parameter_bytes + 4*params.n*params.m
    master = 8 + 4 + public + 2*params.m_bar*params.w
    key = 8 + 4 + public + 4 + params.identity_max_bytes + params.salt_bytes + 4*params.m*params.w
    base = len(MAGIC) + 1 + 32 + 2 + 2 + 4 + parameter_bytes + 8 + master
    entry = 4 + params.identity_max_bytes + 1 + 8 + key
    return dict(public=public, master=master, signing_key=key,
                snapshot=base + max_users*entry)


def _preflight(params: Params, max_users: int) -> int:
    bounds = state_size_bounds(params, max_users)
    if max(bounds.values()) > MAX_STATE_BYTES:
        raise IssuerCapacityError("advertised target issuer capacity exceeds the 4 GiB snapshot budget")
    return bounds["snapshot"]


def _params(raw: bytes) -> Params:
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate parameter field")
            result[name] = value
        return result
    record = json.loads(raw, object_pairs_hook=unique,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite parameter")))
    params = Params.from_record(record)
    if params.context() != raw:
        raise ValueError("noncanonical parameter snapshot")
    return params


def _read(handle, count: int) -> bytes:
    if type(count) is not int or not 0 <= count <= MAX_STATE_BYTES:
        raise ValueError("invalid bounded snapshot field")
    raw = handle.read(count)
    if len(raw) != count:
        raise ValueError("truncated issuer snapshot")
    return raw


def _length(handle, width: int, maximum: int, *, empty=False) -> int:
    count = int.from_bytes(_read(handle, width), "big")
    if count > maximum or (count == 0 and not empty):
        raise ValueError("snapshot field exceeds its public byte budget")
    return count


def _identity(value, params=None):
    return validate_identity(value, max_bytes=1 << 20 if params is None else params.identity_max_bytes)


@dataclass(repr=False)
class _Snapshot:
    master: MasterSecret = field(repr=False)
    max_users: int
    entries: dict = field(default_factory=dict, repr=False)
    status: str = "ready"

    def chunks(self):
        public, params = self.master.public_key, self.master.public_key.params
        _preflight(params, self.max_users)
        bounds = state_size_bounds(params, self.max_users)
        if self.status not in _STATE_STATUS or len(self.entries) > self.max_users:
            raise IssuerStateError("invalid target issuer status or entry count")
        if type(public.context) is not bytes or len(public.context) != 32:
            raise IssuerStateError("invalid target issuer public context")
        yield MAGIC
        yield bytes((_STATE_STATUS[self.status],))
        yield public.context
        yield struct.pack(">HH", self.max_users, len(self.entries))
        raw_params = params.context()
        yield struct.pack(">I", len(raw_params))
        yield raw_params
        raw_master = self.master.to_bytes()
        if not 0 < len(raw_master) <= bounds["master"]:
            raise IssuerStateError("target master exceeds its wire budget")
        yield struct.pack(">Q", len(raw_master))
        yield raw_master
        del raw_master
        for identity, (status, key) in sorted(self.entries.items()):
            identity = _identity(identity, params)
            if status not in _ENTRY_STATUS or (status in _COMPLETE_ENTRIES) != (key is not None):
                raise IssuerStateError("invalid target issuer ledger entry")
            if key is not None and (type(key) is not SigningKey or key.identity != identity
                                    or key.public_key.context != public.context
                                    or key.public_key.params != params):
                raise IssuerStateError("target ledger key context or identity mismatch")
            yield struct.pack(">I", len(identity))
            yield identity
            yield bytes((_ENTRY_STATUS[status],))
            raw_key = b"" if key is None else key.to_bytes()
            if len(raw_key) > bounds["signing_key"]:
                raise IssuerStateError("target signing key exceeds its wire budget")
            yield struct.pack(">Q", len(raw_key))
            yield raw_key
            del raw_key

    def to_bytes(self):
        """Convenience for small fixtures; production writes ``chunks`` directly."""
        raw = b"".join(self.chunks())
        if not 0 < len(raw) <= MAX_STATE_BYTES:
            raise IssuerStateError("target issuer snapshot exceeds its byte budget")
        return raw

    @classmethod
    def read_from(cls, handle, total: int):
        try:
            if not 0 < total <= MAX_STATE_BYTES or _read(handle, len(MAGIC)) != MAGIC:
                raise ValueError("invalid target issuer snapshot header")
            state = _read(handle, 1)[0]
            if state not in _STATE_STATUS.values():
                raise ValueError("invalid target issuer state")
            context = _read(handle, 32)
            max_users, count = struct.unpack(">HH", _read(handle, 4))
            params = _params(_read(handle, _length(handle, 4, MAX_PARAMS_BYTES)))
            maximum = _preflight(params, max_users)
            bounds = state_size_bounds(params, max_users)
            if count > max_users or total > maximum:
                raise ValueError("target issuer ledger exceeds its public capacity")
            master_count = _length(handle, 8, bounds["master"])
            master_start = handle.tell()
            if master_start + master_count > total:
                raise ValueError("truncated target master")
            handle.seek(master_count, os.SEEK_CUR)
            previous, entries = None, []
            # Inspect statuses, ordering and lengths before decoding secrets.
            for _ in range(count):
                identity = _identity(_read(handle, _length(handle, 4, params.identity_max_bytes)), params)
                if previous is not None and identity <= previous:
                    raise ValueError("duplicate or unsorted target identity")
                previous = identity
                status = _read(handle, 1)[0]
                if status not in _ENTRY_STATUS.values():
                    raise ValueError("invalid target ledger status")
                key_count = _length(handle, 8, bounds["signing_key"], empty=True)
                if (status in _COMPLETE_ENTRY_CODES) != bool(key_count):
                    raise ValueError("invalid target key presence")
                key_start = handle.tell()
                if key_start + key_count > total:
                    raise ValueError("truncated target key")
                handle.seek(key_count, os.SEEK_CUR)
                entries.append((identity, status, key_start, key_count))
            if handle.tell() != total:
                raise ValueError("appended target snapshot bytes")
            if state != _STATE_STATUS["ready"] or any(
                    status not in _COMPLETE_ENTRY_CODES
                    for _, status, _, _ in entries):
                raise IssuerPendingError("target issuer ledger is unfinished; automatic retry is blocked")
            # Check embedded public roots/identities before either private
            # trapdoor decoder performs expensive target-sized algebra.
            handle.seek(master_start)
            if _read(handle, 8) != b"WPTMS001":
                raise ValueError("wrong target master kind")
            public_count = _length(handle, 4, bounds["public"])
            if public_count > master_count - 12:
                raise ValueError("master public field exceeds component")
            public_raw = _read(handle, public_count)
            public = PublicKey.from_bytes(public_raw)
            if public.params != params or public.context != context:
                raise ValueError("target master public context mismatch")
            for identity, _, start, size in entries:
                handle.seek(start)
                if _read(handle, 8) != b"WPTSK001":
                    raise ValueError("wrong target user key kind")
                key_public_count = _length(handle, 4, bounds["public"])
                if key_public_count > size - 12 or _read(handle, key_public_count) != public_raw:
                    raise ValueError("target issued key public context mismatch")
                identity_count = _length(handle, 4, params.identity_max_bytes)
                if handle.tell() + identity_count > start + size or _read(handle, identity_count) != identity:
                    raise ValueError("target issued identity mismatch")
            handle.seek(master_start)
            master = MasterSecret.from_bytes(_read(handle, master_count))
            result = cls(master, max_users)
            for identity, status, start, size in entries:
                handle.seek(start)
                key = SigningKey.from_bytes(_read(handle, size))
                if key.identity != identity or key.public_key.to_bytes() != public_raw:
                    raise ValueError("target issued key identity or public context mismatch")
                result.entries[identity] = (_ENTRY_NAMES[status], key)
            return result
        except IssuerPendingError:
            raise
        except Exception:
            raise IssuerStateError("invalid target Wang-PW issuer snapshot") from None

    @classmethod
    def from_bytes(cls, raw):
        if type(raw) is not bytes:
            raise IssuerStateError("target issuer bytes required")
        return cls.read_from(io.BytesIO(raw), len(raw))


class FixedIssuer(_legacy.FixedIssuer):
    """Persistent fixed policy; raw ``Backend.key_extract`` remains randomized."""
    def __init__(self, path, backend=None):
        if backend is None:
            from .backend import Backend
            backend = Backend()
        super().__init__(path, backend)

    def _atomic_write(self, snapshot):
        if type(snapshot) is not _Snapshot:
            raise TypeError("target issuer snapshot required")
        target = self.path / STATE_FILE
        if os.path.lexists(target):
            _legacy._plain_file(target)
        descriptor, name = tempfile.mkstemp(dir=self.path, prefix=".wang-pw-target-", suffix=".tmp")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                total = 0
                for chunk in snapshot.chunks():
                    total += len(chunk)
                    if total > MAX_STATE_BYTES:
                        raise IssuerCapacityError("target issuer snapshot exceeds its total byte budget")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            _legacy._sync_directory(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _block(self, snapshot=None):
        try:
            if not os.path.lexists(self.path / PENDING_FILE):
                self._begin()
        except BaseException:
            pass
        if snapshot is not None:
            snapshot.status = "failed"
            try:
                self._atomic_write(snapshot)
            except BaseException:
                pass

    def _load(self):
        self._check_pending()
        path = self.path / STATE_FILE
        info = _legacy._plain_file(path)
        if not 0 < info.st_size <= MAX_STATE_BYTES:
            raise IssuerStateError("target issuer snapshot exceeds its byte limit")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or not 0 < opened.st_size <= MAX_STATE_BYTES
                    or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                raise IssuerStateError("target issuer is not the same bounded ordinary file")
            snapshot = _Snapshot.read_from(handle, opened.st_size)
            after = os.fstat(handle.fileno())
            if (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
                raise IssuerStateError("target issuer snapshot changed while reading")
            return snapshot

    def initialize(self, params: Params, *, max_users=None):
        if type(params) is not Params:
            raise TypeError("exact Wang-PW target parameters required")
        if max_users is None:
            max_users = 4 if params.is_debug else 1
        _preflight(params, max_users)
        self._directory(create=True)
        self._check_empty()
        with self._locked():
            self._check_empty()
            snapshot = None
            try:
                self._begin()
                public, master = self.backend.setup(params)
                if (type(public) is not PublicKey or type(master) is not MasterSecret
                        or public.params != params or public.to_bytes() != master.public_key.to_bytes()):
                    raise IssuerStateError("target setup returned inconsistent public keys")
                try:
                    master = MasterSecret.from_bytes(master.to_bytes())
                except Exception:
                    raise IssuerStateError("target setup returned invalid private state") from None
                snapshot = _Snapshot(master, max_users)
                self._atomic_write(snapshot)
                self._finish()
                return snapshot.master.public_key
            except BaseException:
                self._block(snapshot)
                raise

    def adopt_existing(self, master: MasterSecret, signing_keys, *, max_users=None):
        """Administratively import existing keys without Setup or extraction.

        Imported entries remain distinguishable from keys issued by this
        service. Canonical decoding checks the exact root/key equations and
        identity bindings; it does not attest to their original sampling law,
        Gram--Schmidt quality, or any previous issuance history. The supplied
        keys must be a nonempty, capacity-bounded iterable of SigningKey.
        Cryptographic randomness and native sampling are never requested.
        """
        if type(master) is not MasterSecret or type(master.public_key) is not PublicKey:
            raise TypeError("exact Wang-PW target master secret required")
        public, params = master.public_key, master.public_key.params
        if type(params) is not Params:
            raise TypeError("exact Wang-PW target parameters required")
        if max_users is None:
            max_users = 4 if params.is_debug else 1
        _preflight(params, max_users)
        public_raw = public.to_bytes()
        entries = {}
        for key in signing_keys:
            if len(entries) >= max_users:
                raise IssuerCapacityError("target imported keys exceed the advertised identity capacity")
            if type(key) is not SigningKey:
                raise TypeError("exact Wang-PW target signing keys required")
            identity = _identity(key.identity, params)
            if identity in entries:
                raise IssuerStateError("duplicate imported identity")
            if (type(key.public_key) is not PublicKey or key.public_key.params != params
                    or key.public_key.to_bytes() != public_raw):
                raise IssuerStateError("imported key public context or parameters mismatch")
            entries[identity] = ("imported", key)
        if not entries:
            raise ValueError("at least one existing signing key is required")
        self._directory(create=True)
        self._check_empty()
        with self._locked():
            self._check_empty()
            snapshot = None
            try:
                self._begin()
                try:
                    checked_master = MasterSecret.from_bytes(master.to_bytes())
                    checked_entries = {}
                    for identity, (_, key) in entries.items():
                        checked_key = SigningKey.from_bytes(key.to_bytes())
                        if (checked_key.identity != identity
                                or checked_key.public_key.to_bytes() != public_raw):
                            raise ValueError("imported key changed canonical binding")
                        checked_entries[identity] = ("imported", checked_key)
                    if checked_master.public_key.to_bytes() != public_raw:
                        raise ValueError("imported master changed canonical binding")
                except Exception:
                    raise IssuerStateError("imported Wang-PW material failed canonical validation") from None
                snapshot = _Snapshot(checked_master, max_users, checked_entries)
                self._atomic_write(snapshot)
                self._finish()
                return snapshot.master.public_key
            except BaseException:
                self._block(snapshot)
                raise

    def key_origin(self, identity):
        """Return 'imported' or 'issued' for an existing key, without issuance."""
        identity = _identity(identity)
        self._existing()
        with self._locked():
            snapshot = self._load()
            identity = _identity(identity, snapshot.master.params)
            if identity not in snapshot.entries:
                raise IssuerStateError("identity has no stored Wang-PW key")
            return snapshot.entries[identity][0]

    def key_extract(self, identity):
        identity = _identity(identity)
        self._existing()
        with self._locked():
            snapshot = self._load()
            public = snapshot.master.public_key
            identity = _identity(identity, public.params)
            if identity in snapshot.entries:
                return snapshot.entries[identity][1]
            if len(snapshot.entries) >= snapshot.max_users:
                raise IssuerCapacityError("target fixed issuer identity capacity exhausted")
            self._begin()
            snapshot.entries[identity] = ("pending", None)
            try:
                self._atomic_write(snapshot)
                key = self.backend.key_extract(snapshot.master, identity)
                if (type(key) is not SigningKey or key.identity != identity
                        or key.public_key.to_bytes() != public.to_bytes()):
                    raise IssuerStateError("target extraction returned an inconsistent key")
                try:
                    key = SigningKey.from_bytes(key.to_bytes())
                except Exception:
                    raise IssuerStateError("target extraction returned an invalid signing key") from None
                snapshot.entries[identity] = ("issued", key)
                self._atomic_write(snapshot)
                self._finish()
                return key
            except BaseException:
                snapshot.entries[identity] = ("failed", None)
                self._block(snapshot)
                raise


__all__ = ["FixedIssuer", "IssuerStateError", "IssuerPendingError", "IssuerCapacityError", "state_size_bounds"]
