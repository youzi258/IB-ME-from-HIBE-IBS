# Wang–PW native finite integer sampler

`gaussian.cpp` exports ABI version 1, used through the sibling `native.py`.
Build dependencies are a C++17 compiler, OpenMP, MPFR, GMP and OpenSSL crypto.
The bridge builds with `-fno-fast-math -ffp-contract=off` in a temporary cache,
not in the source tree. A Linux target with a 64-bit `long` and at least 64
long-double significand bits is required. Compiled libraries are not committed.

`IBME_WANG_PW_TARGET_NATIVE` selects an existing absolute `.so` path. An
explicit path never falls back to compilation. Its adjacent `<filename>.json`
receipt must bind ABI version 1, the current C++ source SHA-256 and the library
SHA-256. The loaded library must independently export the matching ABI and
compiled source-hash string. `build_native()` creates this pair; transfer both
files together. Without the environment variable the bridge builds and checks
its temporary-cache copy automatically. These bindings detect stale or mixed
build artifacts; they do not authenticate an untrusted toolchain or library.

For the input binary64 values `center=c` and `sigma=s>0`, the sampler assigns
the integer weight

```text
w(x) = floor(2^mass_bits * exp(-((x-c)^2 - dist(c,Z)^2)/(2*s^2)))
```

to `x` in the finite window
`floor(c) ± (ceil(tail_sigma*s)+1)`. It samples those integer masses by
rejection from a mixture of uniform integer shells. Each shell receives a
directed upper bound on the largest Gaussian weight in that shell. All shell
mass arithmetic uses four fixed 64-bit limbs. Gaussian evaluations use an
MPFR directed lookup table; uncertain comparisons use MPFR directed arithmetic
at the requested precision. A decision still unresolved at that precision
fails explicitly. The sampler never draws a continuous normal or rounds one.

The defaults are `tail_sigma=20`, `mass_bits=192`, `precision_bits=256`, and
`max_attempts=4096`. Supported mass precision is 32–192 bits; MPFR precision
must be at least mass precision plus 64 bits and at most 4096 bits. Centers
are bounded by `2^50`, integer window radii by `2^40`, threads by 256, and
standalone batches by `2^32` values. A uniform-integer rejection subroutine
has its own 4096-proposal budget. All failures raise `SamplingError`; a partial
output is not returned by the Python bridge.

Production entry points obtain a new 256-bit master seed from OpenSSL
`RAND_bytes`. Domain-separated SHA-256 key derivation initializes ChaCha20
streams. Standalone draws use independent thread streams; deterministic
results require the same thread count. GPV uses an independent stream for
each column, so its fixed-seed output is independent of OpenMP scheduling and
thread count. Fixed caller seeds are accepted only with `test_only=True`.

`sample_gpv` performs the complete backward GPV loop in C++ over a square
column basis. Integer updates use checked 128-bit intermediates and 64-bit
outputs. Input Gram–Schmidt vectors, norm data and center updates remain
floating point. This implementation does not certify their error or a total
chain variation bound. Window truncation, dyadic weight quantization,
finite-precision center computation, rejection failures, and the original
paper's Gaussian-width convention remain distinct items in parameter and
implementation reporting. This code makes no security-level claim.
