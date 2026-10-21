# Wang–PW s0=4 monitored lifecycle

**2026-10-20 用户确认的比较口径：** 本项目暂按约115位量子安全的工作假设开展实现与比较；当前配置的具体攻击成本尚未复核。

This directory contains a real research implementation driver. It calls the
new `ibme.ibs.wang_pw_target.Backend` and compact canonical objects, not the
isolated PR67 random-target equation probe. Setup root Gaussian sampling and
GPV have been reimplemented using the finite native integer sampler. The
root Gaussian parameter is fixed at the paper-convention width `s0=4`, with
standard deviation `4/sqrt(2*pi)`. Existing optimization/prototype files are
preserved elsewhere.

The experiment does not add a security proof. The selected papers' security
is the project's working premise. Actual parameter and implementation gaps
remain explicit: finite Gaussian truncation/quantization, floating QR and
center arithmetic, root/user quality acceptance gates, and the n512
reduction-beta/SIS-estimation obstruction. A complete functional target run
does not turn this candidate into formal security parameters or a NIST level.

## Environment and first run

Complete the separately reviewed `prepare_environment.sh` procedure before
starting server experiments. This driver never installs or downloads
anything. It needs Python, NumPy, SciPy, psutil, the package source and a
working MPFR/GMP/OpenSSL/OpenMP native build. The local WSL Sage development
environment can run its small debug cases independently of server setup.

After installing the prerequisites and making the checkout available, install
the package into the task environment, then compile and inspect both native
components without sampling:

```bash
~/miniconda3/envs/sage/bin/python -m pip install --no-deps --no-build-isolation -e "$TASK_DIRECTORY/repo"
~/miniconda3/envs/sage/bin/python experiments/research/wang_pw_target/finalize_environment.py \
  --task-directory "$TASK_DIRECTORY" --source-commit "$SOURCE_COMMIT" \
  --source-archive "$TASK_DIRECTORY/environment/source.tar.gz"
source "$TASK_DIRECTORY/environment/runtime.env"
```

`TASK_DIRECTORY` denotes the chosen task directory. The generated
`environment-ready.json` schema 2 records package versions, dependency-lock
hashes, native source/binary hashes, actual imported source hashes and the
source archive hash. `SOURCE_COMMIT` is the operator-supplied revision label;
an extracted archive has no Git HEAD, and the finalizer does not independently
prove that its unpacked contents equal a commit. Verify that correspondence
when transferring the frozen archive. Its `ready` status requires successful
imports, the clean fixed-revision estimator checkout, and both native
ABI/metadata checks; it does not claim an algorithm experiment passed.
Earlier schema-1 receipts only cover the historical core environment. A new
preparation/finalization archives and invalidates old active ready/runtime
files before checking; a failed attempt leaves no active ready receipt.
Keep `runtime.env` local to that machine.

Build the native library explicitly before a server run. Transfer/use its
adjacent `.so.json` receipt too; the bridge verifies the current C++ source
hash, binary hash and ABI. Set `IBME_WANG_PW_TARGET_NATIVE` to the returned
absolute `.so` path. The standalone driver can auto-build when that variable
is unset, whereas the public registry requires an explicit selected library.

```bash
export PYTHONPATH=src
export IBME_WANG_PW_TARGET_NATIVE="$(python -c 'from ibme.ibs.wang_pw_target.native import build_native; print(build_native())')"

# First, one real small instance. Defaults are n=2, q=257 and CSPRNG randomness.
python -u -m experiments.research.wang_pw_target.run_lifecycle \
  --profile debug-q257 --output /tmp/wang-debug-q257.json

# Then a q32 arithmetic/debug instance: n=4, not a security configuration.
python -u -m experiments.research.wang_pw_target.run_lifecycle \
  --profile debug-q32 --output /tmp/wang-debug-q32.json
```

The driver executes `setup`, `extract`, `sign`, independent public `verify`,
`restore`, then `sign-restored`. Verification includes wrong identity,
wrong message, changed public context, truncated wire and appended wire.
The restored signer is given the canonical user key, not the master root.
Prepared dense bases are cleared before restoration, and the same backend
object is reused to prevent retaining two large user bases simultaneously.
When private disk storage is selected, `sign-restored` launches a fresh Python
interpreter that receives only the canonical user-key file and message file.
Its signature is saved in private storage and independently verified by the
parent. Its public receipt records that no issuer input was supplied. The
standalone entry point is `sign_independent`; this is process separation of
the implementation, not an OS sandbox for hostile code using the same UID.
Memory-only debug runs retain same-process restored signing and explicitly
record `independent_process=false`.

Debug defaults to canonical in-memory roundtrip. `--test-seed HEX` is allowed
only on debug profiles, must contain 32 bytes, and is labeled deterministic
test evidence. By default every requested repetition creates a new CSPRNG
root; roots run sequentially. `--repetitions 3` requests three complete roots;
the default is one, and a failure stops the batch without replacing that root.

## Target and private state

Target profile fixes `n=512,q=4294967291`. It requires
`--private-state DIRECTORY` outside every Git checkout. The driver creates a
private run directory under that location, then separate `root-001` etc.
directories. Directories use mode 0700, files 0600, files are created
exclusively, and existing artifacts are never overwritten. Existing state
directories with broader access are rejected. Symlink final directories and
symlink wire files are rejected. Keep this storage private and out of delivery
archives. The public output/log must be outside that private directory.

Canonical PK/MSK/SK/signature wires are written during their corresponding
phases, read back from disk, independently parsed, checked, and used for
restored signing. Public reports contain wire byte counts and observations;
they never contain private wires, salts, private-wire hashes or coefficients.
Exact wire sizes come from `wire_sizes(params)` before large allocations.
Disk preflight reserves the calculated requested wires plus 1 GiB margin.
The report's `private_state_requested` records the command-line choice;
successful per-phase wire counts record completed writes. A rejected preflight
does not claim that private state was persisted.

Choose an outer timeout appropriate to the available machine and experiment
budget; it is deliberately not guessed by the driver. After prerequisites
and debug runs pass, for example:

```bash
/usr/bin/time -v -o /absolute/public/wang-target.time.txt \
  timeout --signal=TERM --kill-after=60s 6h \
  python -u -m experiments.research.wang_pw_target.run_lifecycle \
    --profile target --threads 16 --repetitions 1 \
    --private-state /absolute/private/wang-target \
    --output /absolute/public/wang-target.json \
    > /absolute/public/wang-target.console.jsonl 2>&1
```

The `6h` example is an operator-selected cap, not a runtime estimate or
automatic authorization to run a server before environment completion.
An external termination can leave the last public JSON with a running phase;
retain it, the immediate phase log and the outer process's exit/time output.
Do not report a killed phase as passed. Private partial wires are retained.

`--stop-after setup` stops the entire invocation after the first root's Setup;
any later phase can also be selected. It exits zero as a requested partial
run but records `status=stopped` and `requested_lifecycle_complete=false`.
An algorithm, gate, memory or I/O failure exits one and records its phase,
exception type and a public summary. There is no hidden retry, root reselection
or parameter relaxation. CLI usage errors follow argparse's exit code two.

## Evidence and interpretation

`--output` and the optional `--phase-log` must be new distinct filenames.
The default phase log is `<output-stem>.phases.jsonl`. Every phase emits an
immediately flushed JSON start/end record to that log and stdout. The public
JSON is replaced atomically after each phase, so a long run is monitorable.
Timings use the monotonic clock. Phase timings include canonical serialization
and private writes performed in that phase; restoration includes actual disk
reads when private storage is selected.

The public artifact records exact parameters, identity/message byte lengths,
requested/completed root counts, package/platform/CPU/RAM metadata, thread
environment, native binary/source hashes and relevant source-file SHA-256.
It checks source stability at completion. It retains every root's results
and aggregates passed-phase mean/min/max and sample standard deviation when
more than one root is requested; a failed root is never silently replaced.
Phase durations also include their public monitoring/checkpoint overhead.
RSS is sampled using psutil as the sum of the driver and its live descendants at
`--rss-interval` seconds (default .1); a short transient may fall between
samples, and shared pages may be counted repeatedly. The independent signer
also reports its own observed RSS. Retain `/usr/bin/time -v` as a separate
high-water observation. Historical server receipts from `9135ec8` sampled the
driver alone and used same-process restoration; their source hashes preserve
that boundary rather than being rewritten as evidence of the new process path.
Different thread counts and environments are recorded rather than silently
pooled as a fair benchmark.

Always retain `security_claim=none`, `backend_admitted=false`,
`parameters_are_formal=false`, and `nist_security_category=null` until a
separate authorized parameter decision changes them. Functional and negative
tests are implementation evidence, not a security proof.

## Reusing the completed root without reissuing identity keys

Wait for the original lifecycle/supervisor to terminate before starting these
target-size operations. Use a new private output directory and the unchanged
original `public_key.bin`, `master_secret.bin` and `signing_key.bin`; never copy
private inputs or resulting issuer/role state into Git or public evidence.

`run_reused_service` provides independent `--mode adopt` and `--mode recover`
invocations with `--source-directory`, `--state-directory` and canonical
`--identity-hex`. It explicitly imports the existing root/key through
`FixedIssuer.adopt_existing`, retains the `imported` ledger provenance, and
compares the recovered canonical key to its source. Setup, extraction and
cryptographic sampling entry points are disabled. This audits management import
and fixed recovery, not the service's original issuance history or sampling
distribution. Snapshot recovery validates the full secret equations; it is a
target-size operation, not a cheap header read.

`run_reused_combination run --public-key-file ... --signing-key-file ... --state
...` is a separate research-driver CLI over the public SuiteRuntime API. It
imports exactly the original Wang binary identity and canonical user key, creates
only a real LATTE author-profile root and two receiver keys, then runs separate
role processes. It needs one fresh Wang signature; restart, identity-mismatch
and wire/OTS-replacement checks reuse that ciphertext. Role state contains no
master. This remains distinct from the general `ibme.cli` target-size test.
The lifecycle's original 64-byte identity is binary. Renaming that identity
would require a different extraction and is not a valid reuse of the original
user key.

Both drivers print public JSON without raw exception messages. Run them under
the existing external resource supervisor at target size, sequentially with the
original experiment. Preserve failure receipts and partial private state; do not
restart failed operations or rerun Setup/Extract to obtain a success.

## General CLI reuse of existing canonical roles

The general CLI keeps its default printable UTF-8 input. Explicit
`--identity-encoding hex` decodes canonical lowercase hex into the original
identity bytes, including NUL or non-UTF-8 bytes. Length limits apply after
decoding; whitespace, odd-length text and noncanonical hex are rejected.
The selected encoding applies to every identity in that command. For example,
use `426f62` for receiver `Bob` when the same command uses a hex sender.

`ibme import-role --suite-file ... --public-key-file ... --sender-key-file ...
--state NEWDIR` imports one canonical protocol SenderKey. Replace the sender
option with `--receiver-key-file` for one canonical protocol ReceiverKey.
These inputs are composite protocol objects, not bare primitive secret files.
The explicit suite must match all public parameters and the selected codecs.
No master is imported and no Setup, Extract or Sign is performed by import.

The output retains v2 state envelopes with explicit imported-role provenance
and `master_persisted_before_key_publication=false`. Import is a management
operation, not certification of generation history or distribution. The
existing issuance lock and `msk.bin.pending` cover publication. Failure retains
the marker and partial state for inspection. Existing state is not overwritten
or resumed. Imported state can only restore its registered identity and role;
missing/damaged keys or a new identity never trigger extraction, even if a
master file is subsequently placed there. Any `msk.bin` entry in imported role
state blocks all role commands before loading a runtime. Existing receiver-cache transactions
remain in use. No malicious rollback or hard-power-loss guarantee is added.

After `run_reused_combination run` succeeds, its prepared role directories can
be reused without another root or extraction:

```bash
python -B -m experiments.research.wang_pw_target.run_reused_cli run \
  --source-directory /absolute/private/completed-reuse-combination \
  --state /absolute/private/new-general-cli-reuse
```

This harness invokes the general CLI parser and dispatch in separate
interpreters, with Wang Setup/Extract explicitly disabled by the harness.
It imports the three existing roles, preserves the original binary sender,
and requests one fresh encryption/signature. Recovery, identity-mismatch and
wire/OTS-replacement checks reuse that ciphertext. It captures CLI stdout and
stderr privately and emits bounded public receipts; the harness protection
does not change normal CLI algorithm semantics. Run sequentially under the
resource supervisor after the original lifecycle terminates, with a fresh
private target directory. A failed child stops the chain without retry.
Small-profile tests and actual n512 acceptance must be recorded separately.

## Bounded independent-signing diagnostics

The independent signer adds optional `operation_stage` and `sign_diagnostic`
fields to its existing v1 public JSON receipt. The latter contains only
`stage`, `failure_reason`, and `native_code`. Stages denote the last operation
entered, not a completed operation. Backend stages separate user-basis
construction, numerical QR, the fixed GS gate, the delegated public-matrix
check, salt/hash/particular construction, native GPV, signature construction,
and final verification. The process stage also distinguishes private reads,
decoding, signature encoding, observations, and private publication.

Only fixed enumerated reasons and strict integer native return codes 1--6
are public. Unknown codes and diagnostic-reader failures become fixed
placeholders. Exception messages, dynamic exception class names, extra
diagnostic fields, paths, salts, coefficients, and newly measured secret-key
statistics are not forwarded. The lifecycle parent filters these fields
again; old receipts without them remain readable. Native code 6 is a general
C++ exception category and does not by itself identify an allocation failure.

Diagnostics neither change sampling nor add a retry. They do not identify
the reason for an earlier receipt that recorded only `SamplingError`, and
the previously frozen server checkouts are not modified by this local patch.
The one-shot continuation controller remains bound to its earlier frozen
source; it must not be treated as deployment of this diagnostic patch.
