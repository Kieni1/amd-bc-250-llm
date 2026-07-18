#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC="$ROOT/packaging/bc250-llm-server.spec"
fail=0

bad() {
  echo "ERROR: $*" >&2
  fail=1
}

required=(
  README.md docs/TLDR.md VERSION Makefile .github/workflows/build-rpm.yml
  packaging/bc250-llm-server.spec packaging/bc250-llm-server.tmpfiles
  packaging/wrappers/bc250-40cu licenses/LICENSE
  licenses/THIRD_PARTY_NOTICES.md licenses/40CU-LICENSE-NOTICE
  governor/config.toml governor/cyan-skillfish-governor-smu.service
  governor/com.cyanskillfish.Governor.conf containers/llm.network
  containers/tika.container containers/open-webui.container
  nginx/bc250-llm-server.conf nginx/websocket-map.conf
  system/install-ollama.sh system/install-cu-manager.sh
  system/memory-profile.sh system/swap-profile.sh system/ollama.service.d-override.conf
  models/fetch-models.sh models/model-sources.sh
  experiments/fetch-experiments.sh experiments/experiment-sources.sh
  task-model/Modelfile task-model/setup-gemma-1b-task.sh
  scripts/prepare-governor-sources.sh scripts/prepare-40cu-source.sh
  scripts/prepare-live-manager-source.sh patches/40cu-fedora-helper.patch
  scripts/make-source-tarball.sh docs/MEMORY.md docs/CU-UNLOCK.md
  docs/HARDENING.md monitoring/llm-run-diagnose.sh
)
for file in "${required[@]}"; do
  [[ -f "$ROOT/$file" ]] || bad "missing $file"
done

# Extracted and vendored upstream trees are not project code.
while IFS= read -r -d '' file; do
  bash -n "$file" || fail=1
done < <(find "$ROOT" \( -path "$ROOT/.git" -o -path "$ROOT/build" -o -path "$ROOT/dist" -o -path "$ROOT/rpmbuild" -o -path "$ROOT/sources" -o -path "$ROOT/governor-src" -o -path "$ROOT/unlock-src" -o -path "$ROOT/live-manager-src" \) -prune -o -type f -name '*.sh' -print0)

grep_project() {
  grep -RqsE --exclude-dir=.git --exclude-dir=build --exclude-dir=dist --exclude-dir=rpmbuild --exclude-dir=sources --exclude-dir=governor-src --exclude-dir=unlock-src --exclude-dir=live-manager-src "$@"
}

if grep_project --exclude=validate.sh --exclude=verify.sh --exclude='*.orig' 'hf_[A-Za-z0-9]{20,}|WEBUI_ADMIN_PASSWORD=|WEBUI_SECRET_KEY=' "$ROOT"; then
  bad "token or committed Open WebUI secret found"
fi
if grep_project --exclude=validate.sh 'llm_admin|llm\.office\.local' "$ROOT"; then
  bad "site-specific account or hostname remains"
fi
if grep_project --exclude='*.md' --exclude='*.example' --exclude='*.orig' --exclude=validate.sh --exclude=bc250-wake.service '/home/[^/]+|/usr/local/bin/wake-bc250\.sh' "$ROOT"; then
  bad "hard-coded operator path remains in packaged executable content"
fi

version="$(<"$ROOT/VERSION")"
spec_version="$(awk '$1=="Version:" {print $2; exit}' "$SPEC")"
spec_release="$(awk '$1=="Release:" {print $2; exit}' "$SPEC")"
release_base="$(sed 's/%{?dist}$//' <<< "$spec_release")"
changelog_nevr="$(awk '/^%changelog/{seen=1; next} seen && /^\*/ {print $NF; exit}' "$SPEC")"
[[ "$version" == "$spec_version" ]] || bad "VERSION and spec Version differ"
[[ "$changelog_nevr" == "$spec_version-$release_base" ]] || bad "top changelog entry does not match Version-Release"

governor_commit="60ab6e5b354f01f287c73d920990dcd618a674cc"
unlock_commit="6c3969ddee40e894297869e6ca30537f274619cb"
live_manager_commit="8eb45f07810af738f3e4945ea0cc29d399e378a6"
governor_sha="15fa19ce8fdc13dd629977144f24f8cca8bf1a1e8c65e61820cd89d6ca02bfd3"
unlock_sha="803968cebaddf164ecf7e9c63f109b0d2db973254f44be9f77fe6235568992ba"
live_manager_sha="50393641e8abff46d2596f4167d5a43f329f8a7f9a8c8e8dbd697f60145cc020"
grep -Fqx "%global governor_commit $governor_commit" "$SPEC" || bad "governor commit differs in spec"
grep -Fqx "%global unlock_commit $unlock_commit" "$SPEC" || bad "40-CU commit differs in spec"
grep -Fqx "%global live_manager_commit $live_manager_commit" "$SPEC" || bad "CU live-manager commit differs in spec"
grep -Fq "COMMIT=\"$governor_commit\"" "$ROOT/scripts/prepare-governor-sources.sh" || bad "governor source script commit differs"
grep -Fq "SOURCE_SHA256=\"$governor_sha\"" "$ROOT/scripts/prepare-governor-sources.sh" || bad "governor source checksum differs"
grep -Fq "COMMIT=\"$unlock_commit\"" "$ROOT/scripts/prepare-40cu-source.sh" || bad "40-CU source script commit differs"
grep -Fq "SOURCE_SHA256=\"$unlock_sha\"" "$ROOT/scripts/prepare-40cu-source.sh" || bad "40-CU source checksum differs"
grep -Fq "COMMIT=\"$live_manager_commit\"" "$ROOT/scripts/prepare-live-manager-source.sh" || bad "CU live-manager source script commit differs"
grep -Fq "SOURCE_SHA256=\"$live_manager_sha\"" "$ROOT/scripts/prepare-live-manager-source.sh" || bad "CU live-manager source checksum differs"

grep -Fqx 'License:        GPL-2.0-only AND MIT' "$SPEC" || bad "main RPM license expression differs"
grep -Fq 'Source3:        bc250-40cu-unlock-%{unlock_commit}.tar.gz' "$SPEC" || bad "pinned 40-CU Source3 is missing"
grep -Fq 'Source4:        bc250-cu-live-manager-%{live_manager_commit}.tar.gz' "$SPEC" || bad "pinned CU live-manager Source4 is missing"
grep -Fq 'README.md TLDR.md' "$SPEC" || bad "TLDR.md is not installed by the RPM"
if grep -qE '^%package 40cu|^%files 40cu' "$SPEC"; then
  bad "obsolete 40-CU subpackage remains"
fi
owned_paths=(
  '%{_bindir}/bc250-40cu'
  '%{_bindir}/bc250-cu-live-manager'
  '%{_bindir}/llm-run-diagnose'
  '%{project_libexec}/40cu/'
  '%{project_share}/40cu/'
  '%{project_share}/cu-live-manager/'
  '%dir %{_unitdir}/ollama.service.d'
  '%config(noreplace) %{_sysconfdir}/nginx/conf.d/00-bc250-websocket-map.conf'
)
for owned in "${owned_paths[@]}"; do
  grep -Fq "$owned" "$SPEC" || bad "missing RPM ownership: $owned"
done
grep -Fq '%license licenses/LICENSE governor-src/LICENSE licenses/40CU-LICENSE-NOTICE' "$SPEC" || bad "40-CU notice is not owned by the main RPM"
grep -Eq '^Requires:[[:space:]]+umr$' "$SPEC" || bad "CU live-manager runtime dependency umr is missing"
grep -Fq 'patch -d unlock-src -p1 < patches/40cu-fedora-helper.patch' "$SPEC" || bad "Fedora 40-CU helper fix is not applied"
grep -Fq 'systemctl try-restart tika.service open-webui.service' "$SPEC" || bad "upgrade does not restart refreshed Quadlets"
grep -Fq 'if [ "$1" -gt 1 ]; then' "$SPEC" || bad "install/upgrade behavior is not distinguished"
grep -Fq 'rm -rf %{buildroot}' "$SPEC" && bad "obsolete buildroot cleanup remains"

if sed -n '/^%post$/,/^%files$/p' "$SPEC" | grep -Eq 'bc250-40cu|bc250_cc_write_mode|amdgpu\.ko|depmod|dracut|reboot|grubby'; then
  bad "RPM scriptlets manipulate the kernel or CU routing"
fi

grep -Fq 'ttm.pages_limit=4194304' "$ROOT/system/memory-profile.sh" || bad "full TTM profile is missing"
grep -Fq 'PARAM_NAMES="amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask"' "$ROOT/system/memory-profile.sh" || bad "legacy memory arguments are not removed"
grep -Fq 'sudo xfs_growfs /' "$ROOT/system/swap-profile.sh" || bad "swap helper does not explain an unexpanded XFS root"
if grep -RqsE 'ttm\.pages_limit=3959290|amdgpu\.gttsize=(14750|15258)' "$ROOT/system" "$ROOT/docs/MEMORY.md" "$ROOT/README.md"; then
  bad "obsolete memory profile remains in active documentation"
fi

if ! python3 - "$ROOT" <<'PY'
import pathlib, sys, tomllib, xml.etree.ElementTree as ET
root = pathlib.Path(sys.argv[1])
try:
    with (root / "governor/config.toml").open("rb") as f:
        tomllib.load(f)
    ET.parse(root / "governor/com.cyanskillfish.Governor.conf")
except (OSError, ValueError, ET.ParseError) as error:
    print(f"ERROR: governor config parse failed: {error}", file=sys.stderr)
    raise SystemExit(1)
print("Governor TOML and D-Bus XML parsed.")
PY
then
  bad "governor configuration is not valid TOML/XML"
fi

governor_min="$(awk '/^\[frequency-range\]/{section=1; next} /^\[/{section=0} section && $1=="min" {print $3; exit}' "$ROOT/governor/config.toml")"
[[ "$governor_min" == 350 ]] || bad "governor minimum is ${governor_min:-missing}; expected 350"

if ! awk '
  /^\[\[safe-points\]\]/ {
    if (frequency == 2000 && voltage == 960) found=1
    frequency=""; voltage=""
    next
  }
  $1 == "frequency" {frequency=$3}
  $1 == "voltage" {voltage=$3}
  END {
    if (frequency == 2000 && voltage == 960) found=1
    exit found ? 0 : 1
  }
' "$ROOT/governor/config.toml"; then
  bad "governor safe point 2000 MHz / 960 mV is missing"
fi

if ! awk '
  /^\[\[safe-points\]\]/ {
    if (frequency == 350 && voltage == 700) found=1
    frequency=""; voltage=""
    next
  }
  $1 == "frequency" {frequency=$3}
  $1 == "voltage" {voltage=$3}
  END {
    if (frequency == 350 && voltage == 700) found=1
    exit found ? 0 : 1
  }
' "$ROOT/governor/config.toml"; then
  bad "governor safe point 350 MHz / 700 mV is missing"
fi

grep -Fq 'check_governor_limit' "$ROOT/packaging/wrappers/bc250-40cu" && bad "40-CU clock safeguard remains"
grep -Fq 'Clock and voltage policy belongs entirely to the operator' "$ROOT/packaging/wrappers/bc250-40cu" || bad "operator governor policy is undocumented"
grep -Fq 'VERSION="${OLLAMA_VERSION:-0.32.1}"' "$ROOT/system/install-ollama.sh" || bad "Ollama helper version differs"
grep -Fq 'Installer SHA-256:' "$ROOT/system/install-ollama.sh" || bad "Ollama installer audit hash is missing"
grep -Fq 'manager="/usr/bin/bc250-cu-live-manager"' "$ROOT/system/install-cu-manager.sh" || bad "CU manager compatibility helper is not package-local"
grep -Eq 'raw\.githubusercontent|CU_MANAGER_URL|curl .*bc250-cu-live-manager' "$ROOT/system/install-cu-manager.sh" && bad "CU manager compatibility helper still downloads code"

for script in models/fetch-models.sh experiments/fetch-experiments.sh; do
  grep -Fq 'if [[ -z "$HF_TOKEN" ]] && { exec 3<>/dev/tty; } 2>/dev/null; then' "$ROOT/$script" || bad "$script does not prompt through the controlling terminal"
  grep -Fq 'HOME=/var/lib/ollama' "$ROOT/$script" || bad "$script uses the wrong Ollama home"
  grep -Fq 'outside 0-' "$ROOT/$script" || bad "$script silently drops out-of-range selection"
  grep -Fq '[[ "$revision" == latest ]] || revision_args=(--revision "$revision")' "$ROOT/$script" || bad "$script does not support latest and named revisions"
  grep -Fq 'HF_HOME/downloads' "$ROOT/$script" || bad "$script downloads directly into the protected model tree"
done

for script in task-model/setup-gemma-1b-task.sh coding-agent/setup-coding-agent.sh; do
  grep -Fq 'Hugging Face token (Enter for none)' "$ROOT/$script" || bad "$script does not offer an HF token prompt"
  grep -Fq 'exec 3<>/dev/tty' "$ROOT/$script" || bad "$script loses its HF prompt when stdin is redirected"
  grep -Fq 'HF_HOME/downloads' "$ROOT/$script" || bad "$script downloads directly into the protected model tree"
done

grep -Fq 'ttm.pages_limit = 4194304' \
  "$ROOT/monitoring/llm-run-diagnose.sh" ||
  bad "diagnostic script does not expect ttm.pages_limit=4194304"

if grep -Eq '3959290|ttm\.page_pool_size=3959290|amdgpu\.gttsize=15258' \
  "$ROOT/monitoring/llm-run-diagnose.sh"; then
  bad "diagnostic script contains the obsolete memory profile"
fi

while IFS= read -r -d '' modelfile; do
  [[ -n "$(awk -F': ' '/^# Ollama model:/ {print $2; exit}' "$modelfile")" ]] || bad "$modelfile lacks an Ollama title"
  grep -Eq '^# Source: .+ @ .+$' "$modelfile" || bad "$modelfile lacks source metadata"
  grep -Eq '^# GGUF: .+\.gguf$' "$modelfile" || bad "$modelfile lacks GGUF metadata"
  [[ "$(grep -Fxc 'PARAMETER num_gpu 99' "$modelfile")" -eq 1 ]] || bad "$modelfile must set num_gpu 99 exactly once"
  [[ "$(grep -Fxc 'PARAMETER num_keep 256' "$modelfile")" -eq 1 ]] || bad "$modelfile must set num_keep 256 exactly once"
done < <(find "$ROOT/models" "$ROOT/experiments" "$ROOT/coding-agent" "$ROOT/task-model" -maxdepth 1 -name '*Modelfile' -print0)

while read -r kind name repo revision gguf modelfile extra; do
  [[ -z "$extra" ]] || { bad "bad production model example: $name"; continue; }
  path="$ROOT/models/$modelfile"
  [[ -r "$path" ]] || { bad "missing production Modelfile: $modelfile"; continue; }
  [[ "$(awk -F': ' '/^# Ollama model:/ {print $2; exit}' "$path")" == "$name" ]] || bad "$modelfile title differs from the source catalog"
  grep -Fqx "# Source: $repo @ $revision" "$path" || bad "$modelfile source metadata differs"
  grep -Fqx "# GGUF: $gguf" "$path" || bad "$modelfile GGUF metadata differs"
done < <(sed -nE 's/^# (model) ([a-z0-9].*)/\1 \2/p' "$ROOT/models/model-sources.sh")

while read -r kind id name repo revision gguf modelfile extra; do
  [[ -z "$extra" ]] || { bad "bad experiment example: $id"; continue; }
  path="$ROOT/experiments/$modelfile"
  [[ -r "$path" ]] || { bad "missing experiment Modelfile: $modelfile"; continue; }
  [[ "$(awk -F': ' '/^# Ollama model:/ {print $2; exit}' "$path")" == "$name" ]] || bad "$modelfile title differs from the experiment catalog"
  grep -Fqx "# Source: $repo @ $revision" "$path" || bad "$modelfile source metadata differs"
  grep -Fqx "# GGUF: $gguf" "$path" || bad "$modelfile GGUF metadata differs"
  grep -Fqx "FROM /var/llm/gguf-experiments/$id/$gguf" "$path" || bad "$modelfile FROM path differs from the experiment catalog"
done < <(sed -nE 's/^# (ollama_model) ([a-z0-9].*)/\1 \2/p' "$ROOT/experiments/experiment-sources.sh")

grep -Eq '^Image=ghcr\.io/open-webui/open-webui@sha256:[0-9a-f]{64}$' "$ROOT/containers/open-webui.container" || bad "Open WebUI is not digest-pinned"
grep -Eq '^Image=docker\.io/apache/tika@sha256:[0-9a-f]{64}$' "$ROOT/containers/tika.container" || bad "Tika is not digest-pinned"
grep -Fqx 'Memory=2g' "$ROOT/containers/open-webui.container" || bad "Open WebUI memory limit differs"
grep -Fq 'map $http_upgrade $connection_upgrade' "$ROOT/nginx/websocket-map.conf" || bad "nginx WebSocket map is missing"
grep -Fq 'proxy_set_header Connection $connection_upgrade;' "$ROOT/nginx/bc250-llm-server.conf" || bad "nginx proxy does not use WebSocket map"

grep -Fq 'MODEL_REVISION="${TASK_MODEL_REVISION:-latest}"' "$ROOT/task-model/setup-gemma-1b-task.sh" || bad "task model revision is not operator-selectable"
grep -Fq '[[ "$MODEL_REVISION" == latest ]] || revision_args=(--revision "$MODEL_REVISION")' "$ROOT/task-model/setup-gemma-1b-task.sh" || bad "task model does not support latest and named revisions"
grep -Fq 'REVISION="${CODING_AGENT_REVISION:-latest}"' "$ROOT/coding-agent/setup-coding-agent.sh" || bad "coding model revision is not operator-selectable"
grep -Fq '[[ "$REVISION" == latest ]] || args+=(--revision "$REVISION")' "$ROOT/coding-agent/setup-coding-agent.sh" || bad "coding model does not support latest and named revisions"
grep -Fq 'FROM /var/llm/ollama-task/gemma-3-1b-it-UD-Q4_K_XL.gguf' "$ROOT/task-model/Modelfile" || bad "task model does not use its local GGUF"

grep -Fq 'continue-on-error: true' "$ROOT/.github/workflows/build-rpm.yml" && bad "rpmlint is non-gating"
grep -Fq 'set -o pipefail' "$ROOT/.github/workflows/build-rpm.yml" || bad "rpmlint pipeline masks failures"
grep -Fq 'dist/RPM-CONTENTS.txt' "$ROOT/.github/workflows/build-rpm.yml" || bad "CI does not inspect RPM contents"

while IFS= read -r -d '' wrapper; do
  [[ -x "$wrapper" ]] || bad "wrapper is not executable: $wrapper"
  bash -n "$wrapper" || fail=1
done < <(find "$ROOT/packaging/wrappers" -type f -print0)

((fail == 0)) || exit 1
echo "Repository validation passed."
