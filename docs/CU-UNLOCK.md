# Experimental 40-CU tools

The package carries the unlock design and pinned source from
`fduraibi/bc250-40cu-unlock`, commit
`6c3969ddee40e894297869e6ca30537f274619cb`. That repository is a fork of the
current `duggasco/bc250-40cu-unlock` implementation. The project declares the
source GPL-2.0 and its notices are retained.

The RPM itself never compiles or replaces `amdgpu`, changes a module option or
reboots. The guided `install` script performs default-off preparation after the
host is running its newest installed kernel:

1. It installs `kernel-devel-$(uname -r)`.
2. It downloads and caches the matching kernel source when necessary.
3. It patches, compiles and installs the replacement once for that kernel.
4. It rebuilds the matching initramfs and inspects the module inside it.
5. It stops without enabling additional CUs.

The first preparation normally needs a roughly 120 MB kernel-source download
and several minutes of compilation. The source archive is retained under
`/var/cache/bc250-llm-server/40cu`; repeat runs skip both download and build
when the running kernel is already prepared.

## Operator activation

After reading the risks below, the only normal activation command is:

```bash
sudo bc250-40cu enable
```

Type `ENABLE-40CU` at the prompt. The command performs a final preparation
check only when the prepared module or initramfs copy is missing. It then writes
the module option, rebuilds the initramfs once and reboots. After the machine
returns, verify the loaded—not merely installed—module:

```bash
sudo bc250-40cu verify
```

`status` deliberately distinguishes three states: the module installed below
`/usr/lib/modules`, the copy embedded in the initramfs, and the driver actually
running in the kernel. An on-disk module marked `patched` is not proof that it
loaded. If activation is configured but the running driver is stock or absent,
the command prints relevant kernel messages.

```bash
sudo bc250-40cu status
sudo bc250-40cu disable   # mode 0 and reboot; keep the prepared module
sudo bc250-40cu restore   # restore the verified Fedora module backup
```

The preparation rejects a mismatched module version and an initramfs that does
not contain `bc250_cc_write_mode`. It also stops before replacement when Secure
Boot or another policy enforces module signatures and no signed module is
available. Automatic Machine Owner Key enrollment would require another
security-sensitive user workflow, so this testing package does not hide it.

Run the guided installer again after booting a newly updated kernel. It prepares
that exact kernel while preserving the Fedora module backup used by `restore`
and the full purge command.

## Risks

Harvested compute units may be defective. Possible failures include GPU resets,
wrong results, artifacts, boot failures, excess power and overheating. Keep a
second bootable kernel and local console access. Test representative inference
correctness as well as throughput after activation.

Clock and voltage policy remains entirely the operator's responsibility. The CU
tools do not inspect, limit or change the shipped governor configuration.

## Pinned live manager

The RPM also contains the live manager pinned to WinnieLV commit
`8eb45f07810af738f3e4945ea0cc29d399e378a6`. Its repository has no attached
license; that fact is recorded in the third-party notice.

```bash
sudo bc250-40cu
sudo bc250-40cu live-status
sudo bc250-40cu live-full
sudo bc250-40cu health-test MODEL_NAME
sudo bc250-40cu live-stock
```

Running `bc250-40cu` without arguments opens the interactive manager. Live WGP
routing is a separate low-level experiment: a 40/40 routing table can coexist
with stock 24-CU kernel/RADV enumeration. Do not use the live manager as proof
that the replacement module loaded or that inference is correct.

Upstreams:

- <https://github.com/duggasco/bc250-40cu-unlock>
- <https://github.com/fduraibi/bc250-40cu-unlock>
- <https://github.com/WinnieLV/bc250-cu-live-manager>
