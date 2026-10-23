#!/usr/bin/env bash
set -Eeuo pipefail
root="${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
fail=0

need_file() {
  [[ -f "$root/$1" ]] || { echo "ERROR: missing current guidance file: $1" >&2; fail=1; }
}
need_text() {
  local file=$1 text=$2 label=$3
  grep -Fq -- "$text" "$root/$file" || { echo "ERROR: $label" >&2; fail=1; }
}

for file in \
  VERSION release-contract.json WORKBENCH-STATE.json \
  development/README.md development/OWNERSHIP.md \
  development/TESTING-STRATEGY.md development/VALIDATION-MATRIX.md \
  development/DEVELOPMENT-SCOPE.json development/DECISIONS.md; do
  need_file "$file"
done

identity="$(python3 - "$root" <<'PY'
import json, pathlib, re, sys
root=pathlib.Path(sys.argv[1])
version=(root/'VERSION').read_text(encoding='utf-8').strip()
spec=(root/'packaging/bc250-llm-server.spec').read_text(encoding='utf-8')
version_match=re.search(r'^Version:\s*(\S+)\s*$', spec, re.MULTILINE)
release_match=re.search(r'^Release:\s*([^%\s]+)%\{\?dist\}\s*$', spec, re.MULTILINE)
assert version_match and release_match, 'spec Version/Release missing'
spec_version=version_match.group(1); rpm_release=release_match.group(1)
contract=json.loads((root/'release-contract.json').read_text())
workbench=json.loads((root/'WORKBENCH-STATE.json').read_text())
assert spec_version == version
assert contract['package']['version'] == version
assert contract['package']['rpm_release'] == rpm_release
nvr=f"{contract['package']['name']}-{version}-{rpm_release}"
assert workbench['release']['version'] == version
assert workbench['release']['rpm_release'] == rpm_release
assert workbench['release']['nvr'] == nvr
assert workbench['kind']=='release-workbench'
assert contract['authority']['primary']['kind']=='github-actions'
assert contract['authority']['primary']['selection_event']=='workflow_dispatch'
print(nvr)
PY
)" || fail=1

if [[ -n "${identity:-}" ]]; then
  need_text development/VALIDATION-MATRIX.md "Current release identity: \`${identity}\`" 'current NVR missing from validation matrix'
  need_text TLDR.md "$identity" 'current NVR missing from TLDR'
fi
need_text Makefile 'Run blocking Ruff and ShellCheck release preflight' 'make help must describe lint as blocking'
need_text development/VALIDATION-MATRIX.md 'configured rpmlint failure' 'validation matrix omits blocking rpmlint semantics'
need_text development/README.md 'do not need to be rewritten for every RPM release' 'development memory is still coupled to every RPM release'
need_text development/OWNERSHIP.md 'Public product concepts are intentionally fewer' 'repository ownership boundary missing'
need_text development/TESTING-STRATEGY.md 'Do not delete' 'test-retention rule missing'

if [[ -e "$root/development/handovers/scripts/new-sidechat-prompt.txt" ]]; then
  echo 'ERROR: repository-owned sidechat prompt returned; chat handoff prompts are external development workflow' >&2
  fail=1
fi

((fail == 0)) || exit 1
echo 'Current clean-core guidance check: PASS'
